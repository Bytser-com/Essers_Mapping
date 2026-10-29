"""Essers XML mapping prototype: raw historical pairs + new customer XML -> Excel.

Run ``python main.py --preview`` first, then ``python main.py``.
All mapping decisions are proposed by Gemini and require expert approval.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

from dotenv import load_dotenv

from scripts.excel_generator import export_excel
from scripts.experiment_tracker import ExperimentTracker
from scripts.mapping_validator import validate_mappings
from scripts.readprompt import build_mapping_contents, run_gemini
from scripts.xml_parser import (
    discover_historical_pairs,
    parse_xml_files,
    select_historical_examples,
    select_raw_examples,
)

ROOT = Path(__file__).resolve().parent


def save_json(path: Path, data) -> None:
    """Safely save results and checkpoints without partial JSON files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(temp, path)


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def fingerprint_files(files: list[Path]) -> str:
    """Private, content-based dataset version; never stores XML in the experiment log."""
    digest = hashlib.sha256()
    for file in sorted(set(files), key=str):
        digest.update(file.relative_to(ROOT).as_posix().encode('utf-8'))
        digest.update(b'\0')
        with file.open('rb') as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(block)
        digest.update(b'\0')
    return digest.hexdigest()


def code_fingerprint() -> str:
    """Version the actual project code and template, not only the AI prompt."""
    files = [
        ROOT / 'main.py', ROOT / 'scripts' / 'xml_parser.py',
        ROOT / 'scripts' / 'readprompt.py', ROOT / 'scripts' / 'mapping_validator.py',
        ROOT / 'scripts' / 'excel_generator.py', ROOT / 'scripts' / 'experiment_tracker.py',
        ROOT / 'templates' / 'mapping_template.xlsx',
    ]
    return fingerprint_files(files)


def job_signature(settings: dict, dataset_hash: str, prompt_hash: str, code_hash: str) -> str:
    """Identical settings + XML + prompt + code resume the same mapping job."""
    payload = {'settings': settings, 'dataset_sha256': dataset_hash,
               'prompt_sha256': prompt_hash, 'code_sha256': code_hash}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()


def unresolved(target: str) -> dict:
    """Clearly labelled placeholder when Gemini omits a target."""
    return {
        'source_path': '', 'target_path': target,
        'rule_type': 'REVIEW_REQUIRED', 'confidence': 0,
        'requires_review': True, 'review_priority': 'High',
        'reason': 'Gemini did not produce a valid mapping proposal for this target.',
        'evidence': '', 'fixed_value': '', 'transformation': '',
        'condition': '', 'lookup': '', 'loop': '',
        'review_question': 'Which source field or business rule should populate this target?',
        'risk_category': 'Unmapped target', 'validation_issues': [],
    }


def needs_repair(proposals: list[dict], batch: list[dict], source_paths: set[str]) -> list[dict]:
    """Identify omitted, duplicated, or structurally invalid target proposals."""
    valid_rules = {
        'DIRECT', 'FIXED', 'DEFAULT_IF_EMPTY', 'DERIVED', 'CONDITIONAL',
        'LOOKUP', 'LOOP', 'FORMAT_DATE', 'REVIEW_REQUIRED',
    }
    fix = []
    for field in batch:
        path = field['path']
        choices = [p for p in proposals if isinstance(p, dict) and p.get('target_path') == path]
        if len(choices) != 1:
            fix.append(field)
            continue
        proposal = choices[0]
        source = str(proposal.get('source_path') or '').strip()
        rule = str(proposal.get('rule_type') or '').upper().strip()
        if (
            rule not in valid_rules
            or (source and source not in source_paths)
            or (not source and rule not in {'FIXED', 'REVIEW_REQUIRED'})
            or (rule == 'FIXED' and not str(proposal.get('fixed_value') or '').strip())
        ):
            fix.append(field)
    return fix


def main() -> None:
    started = time.perf_counter()
    started_utc = datetime.now(timezone.utc).isoformat(timespec='seconds')
    parser = argparse.ArgumentParser(description='Create an AI source-to-target mapping proposal from XML examples.')
    parser.add_argument('--history-pairs', type=int, default=1,
                        help='Complete original/converted examples from EACH historical company (default 1).')
    parser.add_argument('--source-samples', type=int, default=2,
                        help='Complete raw new-customer XML examples sent to Gemini (default 2).')
    parser.add_argument('--max-source-chars', type=int, default=180000,
                        help='Combined character budget for raw new-customer examples (default 180000).')
    parser.add_argument('--limit-targets', type=int, default=10,
                        help='Number of target fields to propose (default 10, 0 = all).')
    parser.add_argument('--batch-size', type=int, default=10,
                        help='Target fields per Gemini request (default 10).')
    parser.add_argument('--target-segment', default='',
                        help='Optional target segment filter, e.g. E1BPOBDLVITEM.')
    parser.add_argument('--model', default='', help='Optional override for GEMINI_MODEL from .env.')
    parser.add_argument('--preview', action='store_true',
                        help='Show exactly what would be sent, without calling Gemini.')
    args = parser.parse_args()
    if args.history_pairs < 0 or args.source_samples < 1 or args.max_source_chars < 1 or args.limit_targets < 0 or args.batch_size < 1:
        parser.error('history-pairs and limit-targets must be >=0; other numbers must be >=1.')

    load_dotenv(ROOT / '.env')
    model = args.model or os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')

    # Python reads ALL files to discover the valid source/target field paths.
    source_files = sorted((ROOT / 'data' / 'source').rglob('*.xml'))
    if not source_files:
        raise SystemExit('No new-customer XML files in data/source/.')
    pairs = discover_historical_pairs(ROOT / 'data' / 'historical')
    converted_files = [pair['converted_file'] for pair in pairs]
    source_fields = parse_xml_files(source_files)
    all_target_fields = parse_xml_files(converted_files)
    if not source_fields or not all_target_fields:
        raise SystemExit('No XML fields found. Check data/source and data/historical.')
    target_fields = all_target_fields
    if args.target_segment:
        target_fields = [f for f in target_fields if args.target_segment.casefold()
                         in f['path'].rsplit('/', 1)[0].casefold()]
        if not target_fields:
            raise SystemExit(f'No target fields found for segment {args.target_segment!r}.')
    if args.limit_targets:
        target_fields = target_fields[:args.limit_targets]

    # Gemini receives SELECTED complete raw XML files, not all hundreds by default.
    source_docs = select_raw_examples(source_files, args.source_samples, args.max_source_chars)
    historical_docs = select_historical_examples(pairs, args.history_pairs)
    batches = [target_fields[i:i + args.batch_size]
               for i in range(0, len(target_fields), args.batch_size)]
    first_contents = build_mapping_contents(
        source_fields, batches[0], all_target_fields, source_docs, historical_docs
    )
    companies = Counter(pair['company'] for pair in pairs)
    print('Historical pairs found: ' + ', '.join(f'{c}={n}' for c, n in sorted(companies.items())))
    print(f'New customer: {len(source_files)} XML files analyzed by Python; {len(source_fields)} unique source fields.')
    print(f'Target format: {len(converted_files)} historical converted XML files; {len(all_target_fields)} total paths, {len(target_fields)} selected.')
    print(f'Raw customer XMLs provided to Gemini: {len(source_docs)}')
    print('  ' + ', '.join(d['filename'] for d in source_docs))
    print(f'Matched historical pairs provided to Gemini: {len(historical_docs)}')
    print('  ' + (', '.join(f"{p['company']}/{p['pair_id']}" for p in historical_docs) or '(none)'))
    print(f'First request size: {len(first_contents):,} characters; batches: {len(batches)}')
    if len(source_docs) < args.source_samples:
        print('WARNING: Not all requested raw customer examples fit the character budget.')
    if args.preview:
        print('Preview only: no Gemini request and no Excel output.')
        return
    settings = {
        'model': model, 'history_pairs_per_company': args.history_pairs,
        'source_samples': args.source_samples,
        'max_source_chars': args.max_source_chars,
        'target_paths': [f['path'] for f in target_fields],
        'batch_size': args.batch_size,
        'selected_source_docs': [d['filename'] for d in source_docs],
        'selected_history_docs': [p['company'] + '/' + p['pair_id'] for p in historical_docs],
    }
    data_files = [
        *source_files, *converted_files, *[p['original_file'] for p in pairs],
    ]
    dataset_hash = fingerprint_files(data_files)
    prompt_hash = hashlib.sha256((ROOT / 'prompt.txt').read_bytes()).hexdigest()
    code_hash = code_fingerprint()
    signature = job_signature(settings, dataset_hash, prompt_hash, code_hash)
    name = f"history{args.history_pairs}_source{args.source_samples}_targets{len(target_fields)}_{signature[:8]}"
    run_dir = ROOT / 'output' / 'runs' / name
    checkpoints = run_dir / 'checkpoints'
    tracker = ExperimentTracker(
        root=ROOT, run_dir=run_dir,
        started_monotonic=started, started_utc=started_utc, settings={
            'model': model,
            'dataset_version': dataset_hash[:12],
            'prompt_sha256': prompt_hash,
            'code_version': code_hash[:12],
            'history_pairs_per_company': args.history_pairs,
            'historical_pairs_sent': len(historical_docs),
            'source_samples_requested': args.source_samples,
            'source_samples_sent': len(source_docs),
            'target_segment': args.target_segment,
            'targets_requested': len(target_fields),
            'batch_size': args.batch_size,
            'batches_total': len(batches),
        },
    )
    save_json(run_dir / 'run_info.json', {
        **settings,
        'dataset_sha256': dataset_hash,
        'prompt_sha256': prompt_hash,
        'code_sha256': code_hash,
        'source_files_read_by_python': len(source_files),
        'historical_pairs_discovered': len(pairs),
        'raw_customer_examples': [d['filename'] for d in source_docs],
        'historical_examples': [
            {'company': p['company'], 'pair_id': p['pair_id'],
             'original': p['original_filename'], 'converted': p['converted_filename']}
            for p in historical_docs
        ],
        'note': 'The model sees selected raw examples plus full source/target path lists; not every original XML value.',
    })
    print(f'Output folder: {run_dir}')
    print('Experiment tracking: output/experiments.csv and output/experiments/ (global log)')
    stage = 'setup'
    try:
        if not os.getenv('GEMINI_API_KEY'):
            raise SystemExit('GEMINI_API_KEY is missing. Copy .env.example to .env and add your API key.')

        proposals = []
        source_paths = {f['path'] for f in source_fields}
        for index, batch in enumerate(batches, start=1):
            stage = 'gemini'
            target_paths = [f['path'] for f in batch]
            checkpoint = checkpoints / f'batch_{index:04d}.json'
            if checkpoint.is_file():
                try:
                    saved = read_json(checkpoint)
                    if saved.get('signature') == signature and saved.get('targets') == target_paths and isinstance(saved.get('proposals'), list):
                        proposals.extend(saved['proposals'])
                        tracker.restored_batch()
                        print(f'Batch {index}/{len(batches)} restored from checkpoint.')
                        continue
                except (OSError, ValueError, TypeError, AttributeError):
                    print(f'Batch {index}: corrupt checkpoint; regenerating.')

            print(f'Mapping batch {index}/{len(batches)}: {len(batch)} target fields')
            try:
                batch_proposals = run_gemini(
                    source_fields, batch, all_target_fields=all_target_fields,
                    source_documents=source_docs, historical_pairs=historical_docs,
                    model=model, on_event=tracker.event,
                )
                repair = needs_repair(batch_proposals, batch, source_paths)
                if repair:
                    print(f'Gemini omitted or invalidated {len(repair)} target(s); retrying those once.')
                    corrections = run_gemini(
                        source_fields, repair, all_target_fields=all_target_fields,
                        source_documents=source_docs, historical_pairs=historical_docs,
                        model=model, on_event=tracker.event,
                    )
                    corrected = {p.get('target_path'): p for p in corrections
                                 if isinstance(p, dict) and p.get('target_path') in {r['path'] for r in repair}}
                    original = {p.get('target_path'): p for p in batch_proposals
                                if isinstance(p, dict) and p.get('target_path') in target_paths}
                    original.update(corrected)
                    batch_proposals = [original[p] for p in target_paths if p in original]
            except Exception as error:
                if getattr(error, 'code', None) in (429, 503):
                    raise SystemExit(f'Gemini error {error.code}. Completed batches are saved. Run the SAME command to resume.') from None
                raise
            batch_proposals = [p for p in batch_proposals if isinstance(p, dict) and p.get('target_path') in target_paths]
            save_json(checkpoint, {'signature': signature, 'targets': target_paths, 'proposals': batch_proposals})
            proposals.extend(batch_proposals)
            print(f'Saved {len(batch_proposals)} proposal(s).')

        stage = 'validation'
        accepted, rejected, issues = validate_mappings(proposals, source_fields, target_fields)
        found = {p['target_path'] for p in accepted}
        missing = [f['path'] for f in target_fields if f['path'] not in found]
        accepted.extend(unresolved(path) for path in missing)
        if missing:
            print(f'WARNING: {len(missing)} target fields have explicit placeholders (not Gemini mappings).')
        save_json(run_dir / 'mapping_proposals.json', accepted)
        save_json(run_dir / 'rejected_proposals.json', rejected)
        save_json(run_dir / 'validation_issues.json', issues)
        stage = 'excel_export'
        workbook = export_excel(
            accepted, source_fields, source_files, converted_files,
            run_dir / 'mapping_package.xlsx', ROOT / 'templates' / 'mapping_template.xlsx',
            historical_pairs=pairs, selected_historical_examples=historical_docs,
        )
        tracker.finish(status='completed', results={
            'mapping_rows': len(accepted), 'placeholders': len(missing),
            'rejected_proposals': len(rejected), 'structural_issues': len(issues),
            'workbook_path': Path(workbook).relative_to(ROOT).as_posix(),
        })
        print(f'Created Excel: {workbook}')
        print(f'{len(accepted)} rows; {len(missing)} placeholders; {len(rejected)} rejected; {len(issues)} structural issues.')
        print(f'Experiment recorded: output/experiments.csv and output/experiments/{tracker.run_id}.json')
        print('Every proposal needs expert approval; structural checks cannot prove business correctness.')
    except BaseException as error:
        tracker.finish(
            status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed',
            error=error, stage=stage,
        )
        print(f'Experiment failure/interruption recorded: output/experiments/{tracker.run_id}.json')
        raise


if __name__ == '__main__':
    main()
