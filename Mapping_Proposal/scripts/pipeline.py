"""The mapping workflow: raw historical pairs + new customer XML -> Excel.

``preview_mapping`` shows what would be sent to Gemini; ``run_mapping`` performs a
complete run. Both are used by ``main.py`` and can later be used by an API.
All mapping decisions are proposed by Gemini and require expert approval.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import time

from .config import HISTORICAL_DIR, PROMPT_PATH, ROOT, RUNS_DIR, SOURCE_DIR, TEMPLATE_PATH, load_settings
from .errors import ConfigError, InputDataError, QuotaExceededError
from .excel_generator import export_excel
from .historical_evidence import extract_reference_evidence
from .experiment_tracker import ExperimentTracker
from .mapping_validator import find_proposals_needing_retry, validate_mappings
from .models import MappingResult, MappingSettings, PreviewResult
from .readprompt import build_mapping_contents, run_gemini
from .xml_parser import (
    discover_historical_pairs,
    parse_xml_files,
    select_historical_examples,
    select_raw_examples,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers for saving results and versioning a run
# ---------------------------------------------------------------------------

# Files whose content defines the "code version" of a run (used for checkpoints).
CODE_FILES = [
    ROOT / 'main.py',
    *(ROOT / 'scripts' / name for name in (
        'config.py', 'errors.py', 'models.py', 'pipeline.py', 'xml_parser.py',
        'readprompt.py', 'mapping_validator.py', 'historical_evidence.py', 'excel_generator.py',
        'experiment_tracker.py',
    )),
    TEMPLATE_PATH,
    ROOT / 'mapping_schema.json',
]


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
    return fingerprint_files([file for file in CODE_FILES if file.is_file()])


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
        'risk_category': 'HIGH', 'validation_issues': [],
    }


# ---------------------------------------------------------------------------
# Step 1: read data/ and choose what Gemini will see (shared by preview and run)
# ---------------------------------------------------------------------------
@dataclass
class _Inputs:
    """Everything read and selected from data/ for one set of settings."""
    source_files: list[Path]
    pairs: list[dict]
    converted_files: list[Path]
    source_fields: list[dict]
    all_target_fields: list[dict]
    target_fields: list[dict]
    source_docs: list[dict]
    historical_docs: list[dict]
    batches: list[list[dict]]
    first_request_chars: int


def _prepare(settings: MappingSettings) -> _Inputs:
    """Read ALL files to discover valid paths, then select the examples for Gemini."""
    try:
        settings.validate()
    except ValueError as error:
        raise ConfigError(str(error)) from error

    # Python scans ALL files, so the lists of valid source and target paths are
    # complete, even though Gemini only receives a few example documents.
    source_files = sorted(SOURCE_DIR.rglob('*.xml'))
    if not source_files:
        raise InputDataError('No new-customer XML files in data/source/.')
    try:
        pairs = discover_historical_pairs(HISTORICAL_DIR)
        converted_files = [pair['converted_file'] for pair in pairs]
        source_fields = parse_xml_files(source_files)
        all_target_fields = parse_xml_files(converted_files)
    except (ValueError, FileNotFoundError) as error:
        raise InputDataError(str(error)) from error
    if not source_fields or not all_target_fields:
        raise InputDataError('No XML fields found. Check data/source and data/historical.')

    # Optional filters: --target-segment and --limit-targets narrow down which
    # target fields are requested from Gemini.
    target_fields = all_target_fields
    if settings.target_segment:
        target_fields = [f for f in target_fields if settings.target_segment.casefold()
                         in f['path'].rsplit('/', 1)[0].casefold()]
        if not target_fields:
            raise InputDataError(f'No target fields found for segment {settings.target_segment!r}.')
    if settings.limit_targets:
        target_fields = target_fields[:settings.limit_targets]

    # Gemini receives SELECTED complete raw XML files, not all hundreds by default.
    try:
        source_docs = select_raw_examples(source_files, settings.source_samples, settings.max_source_chars)
        historical_docs = select_historical_examples(pairs, settings.history_pairs)
    except ValueError as error:
        raise InputDataError(str(error)) from error
    # Split the requested targets into batches of --batch-size fields per request.
    batches = [target_fields[i:i + settings.batch_size]
               for i in range(0, len(target_fields), settings.batch_size)]
    # Build the first request only to report its size in the preview.
    first_contents = build_mapping_contents(
        source_fields, batches[0], all_target_fields, source_docs, historical_docs
    )
    return _Inputs(
        source_files=source_files, pairs=pairs, converted_files=converted_files,
        source_fields=source_fields, all_target_fields=all_target_fields,
        target_fields=target_fields, source_docs=source_docs,
        historical_docs=historical_docs, batches=batches,
        first_request_chars=len(first_contents),
    )


# ---------------------------------------------------------------------------
# Preview: what would be sent, without calling Gemini
# ---------------------------------------------------------------------------
def _preview(inputs: _Inputs, settings: MappingSettings) -> PreviewResult:
    return PreviewResult(
        companies=dict(sorted(Counter(pair['company'] for pair in inputs.pairs).items())),
        source_file_count=len(inputs.source_files),
        source_field_count=len(inputs.source_fields),
        converted_file_count=len(inputs.converted_files),
        target_path_count=len(inputs.all_target_fields),
        selected_target_count=len(inputs.target_fields),
        source_documents=[d['filename'] for d in inputs.source_docs],
        historical_documents=[f"{p['company']}/{p['pair_id']}" for p in inputs.historical_docs],
        first_request_chars=inputs.first_request_chars,
        batch_count=len(inputs.batches),
        source_budget_warning=len(inputs.source_docs) < settings.source_samples,
    )


def preview_mapping(settings: MappingSettings) -> PreviewResult:
    """Show what a run would send to Gemini, without calling Gemini or writing output."""
    return _preview(_prepare(settings), settings)


def log_preview(preview: PreviewResult) -> None:
    logger.info('Historical pairs found: ' + ', '.join(f'{c}={n}' for c, n in preview.companies.items()))
    logger.info(f'New customer: {preview.source_file_count} XML files analyzed by Python; '
                f'{preview.source_field_count} unique source fields.')
    logger.info(f'Target format: {preview.converted_file_count} historical converted XML files; '
                f'{preview.target_path_count} total paths, {preview.selected_target_count} selected.')
    logger.info(f'Raw customer XMLs provided to Gemini: {len(preview.source_documents)}')
    logger.info('  ' + ', '.join(preview.source_documents))
    logger.info(f'Matched historical pairs provided to Gemini: {len(preview.historical_documents)}')
    logger.info('  ' + (', '.join(preview.historical_documents) or '(none)'))
    logger.info(f'First request size: {preview.first_request_chars:,} characters; batches: {preview.batch_count}')
    if preview.source_budget_warning:
        logger.warning('Not all requested raw customer examples fit the character budget.')


# ---------------------------------------------------------------------------
# Full run: Gemini batches -> validation -> Excel
# ---------------------------------------------------------------------------
def run_mapping(settings: MappingSettings) -> MappingResult:
    """Run the complete workflow and return where the Excel package was written.

    Raises a ``MappingError`` subclass for expected problems (configuration, input
    data, Gemini quota). Completed batches are checkpointed, so rerunning with the
    same settings resumes the job.
    """
    started = time.perf_counter()
    started_utc = datetime.now(timezone.utc).isoformat(timespec='seconds')
    inputs = _prepare(settings)
    log_preview(_preview(inputs, settings))

    # --model on the command line wins over GEMINI_MODEL in .env.
    model = settings.model or load_settings().gemini_model

    # Everything that influences the result. Together with the hashes below it
    # forms the job signature: same signature = same job = checkpoints reusable.
    run_settings = {
        'model': model, 'history_pairs_per_company': settings.history_pairs,
        'source_samples': settings.source_samples,
        'max_source_chars': settings.max_source_chars,
        'target_paths': [f['path'] for f in inputs.target_fields],
        'batch_size': settings.batch_size,
        'selected_source_docs': [d['filename'] for d in inputs.source_docs],
        'selected_history_docs': [p['company'] + '/' + p['pair_id'] for p in inputs.historical_docs],
    }
    data_files = [
        *inputs.source_files, *inputs.converted_files, *[p['original_file'] for p in inputs.pairs],
    ]
    dataset_hash = fingerprint_files(data_files)
    prompt_hash = hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()
    code_hash = code_fingerprint()
    signature = job_signature(run_settings, dataset_hash, prompt_hash, code_hash)
    name = (f"history{settings.history_pairs}_source{settings.source_samples}"
            f"_targets{len(inputs.target_fields)}_{signature[:8]}")
    # Each unique job gets its own folder under output/runs/.
    run_dir = RUNS_DIR / name
    checkpoints = run_dir / 'checkpoints'
    tracker = ExperimentTracker(
        root=ROOT, run_dir=run_dir, job_signature=signature,
        started_monotonic=started, started_utc=started_utc, settings={
            'model': model,
            'dataset_version': dataset_hash[:12],
            'prompt_sha256': prompt_hash,
            'code_version': code_hash[:12],
            'history_pairs_per_company': settings.history_pairs,
            'historical_pairs_sent': len(inputs.historical_docs),
            'source_samples_requested': settings.source_samples,
            'source_samples_sent': len(inputs.source_docs),
            'target_segment': settings.target_segment,
            'targets_requested': len(inputs.target_fields),
            'batch_size': settings.batch_size,
            'batches_total': len(inputs.batches),
        },
    )
    save_json(run_dir / 'run_info.json', {
        **run_settings,
        'dataset_sha256': dataset_hash,
        'prompt_sha256': prompt_hash,
        'code_sha256': code_hash,
        'source_files_read_by_python': len(inputs.source_files),
        'historical_pairs_discovered': len(inputs.pairs),
        'raw_customer_examples': [d['filename'] for d in inputs.source_docs],
        'historical_examples': [
            {'company': p['company'], 'pair_id': p['pair_id'],
             'original': p['original_filename'], 'converted': p['converted_filename']}
            for p in inputs.historical_docs
        ],
        'note': 'The model sees selected raw examples plus full source/target path lists; not every original XML value.',
    })
    logger.info(f'Output folder: {run_dir}')
    logger.info('Experiment tracking: output/experiments.csv and output/experiments/ (global log)')
    # 'stage' records where a failure happened, for the experiment log.
    stage = 'setup'
    try:
        if not load_settings().gemini_api_key:
            raise ConfigError('GEMINI_API_KEY is missing. Add your Gemini API key to ai_tool/.env.')

        proposals = []
        source_paths = {f['path'] for f in inputs.source_fields}
        for index, batch in enumerate(inputs.batches, start=1):
            stage = 'gemini'
            target_paths = [f['path'] for f in batch]
            checkpoint = checkpoints / f'batch_{index:04d}.json'
            tracker.begin_batch(index)
            # A batch that was already completed in an earlier (interrupted) run
            # is loaded from disk instead of calling Gemini again.
            restored = _restore_checkpoint(checkpoint, signature, target_paths, index)
            if restored is not None:
                proposals.extend(restored['proposals'])
                tracker.restored_batch(index, restored.get('metrics'))
                logger.info(f'Batch {index}/{len(inputs.batches)} restored from checkpoint.')
                continue

            logger.info(f'Mapping batch {index}/{len(inputs.batches)}: {len(batch)} target fields')
            try:
                batch_proposals = _map_batch(inputs, batch, source_paths, model, tracker)
            except QuotaExceededError as error:
                # Add the resume hint; all batches finished so far are on disk.
                raise QuotaExceededError(
                    f'{error} Completed batches are saved. Run the SAME command to resume.',
                    code=error.code,
                ) from None
            # Save this batch immediately, so a later failure cannot lose it.
            save_json(checkpoint, {'signature': signature, 'targets': target_paths,
                                   'proposals': batch_proposals, 'metrics': tracker.batch_metrics(index)})
            proposals.extend(batch_proposals)
            logger.info(f'Saved {len(batch_proposals)} proposal(s).')

        # Structural checks only: do the paths and rule types exist? Targets
        # without any usable proposal get a clearly labelled placeholder row.
        stage = 'validation'
        accepted, rejected, issues = validate_mappings(proposals, inputs.source_fields, inputs.target_fields)
        found = {p['target_path'] for p in accepted}
        missing = [f['path'] for f in inputs.target_fields if f['path'] not in found]
        accepted.extend(unresolved(path) for path in missing)
        # Independent, deterministic XML evidence; no extra task for Gemini.
        # Only exact-value candidates from the historical examples Gemini saw.
        reference_evidence = extract_reference_evidence(
            inputs.historical_docs, [f['path'] for f in inputs.target_fields],
        )
        save_json(run_dir / 'historical_evidence_audit.json', {
            'method': 'independent_exact_value_matching',
            'checked_matches': len(reference_evidence),
            'caution': 'Observed value agreement is not proof of a business mapping.',
        })
        logger.info('Historical reference evidence: %d XML-checked candidate(s).',
                    len(reference_evidence))
        warnings = []
        if missing:
            warnings.append(f'{len(missing)} target fields have explicit placeholders (not Gemini mappings).')
            logger.warning(warnings[-1])
        save_json(run_dir / 'mapping_proposals.json', accepted)
        save_json(run_dir / 'rejected_proposals.json', rejected)
        save_json(run_dir / 'validation_issues.json', issues)

        stage = 'excel_export'
        workbook = Path(export_excel(
            accepted, inputs.source_fields, inputs.source_files, inputs.converted_files,
            run_dir / 'mapping_package.xlsx', TEMPLATE_PATH,
            historical_pairs=inputs.pairs, selected_historical_examples=inputs.historical_docs,
            verified_historical_evidence=reference_evidence,
        ))
        # Write one row to output/experiments.csv for this execution.
        tracker.finish(status='completed', results={
            'mapping_rows': len(accepted), 'placeholders': len(missing),
            'rejected_proposals': len(rejected), 'structural_issues': len(issues),
            'workbook_path': workbook.relative_to(ROOT).as_posix(),
            'historical_evidence_checked': len(reference_evidence),
            'historical_evidence_rejected': 0,
        })
        logger.info(f'Created Excel: {workbook}')
        logger.info(f'{len(accepted)} rows; {len(missing)} placeholders; {len(rejected)} rejected; '
                    f'{len(issues)} structural issues.')
        logger.info(f'Experiment recorded: output/experiments.csv and output/experiments/{tracker.run_id}.json')
        logger.info('Every proposal needs expert approval; structural checks cannot prove business correctness.')
        return MappingResult(
            run_id=tracker.run_id, run_dir=run_dir, workbook_path=workbook,
            mapping_rows=len(accepted), placeholders=len(missing),
            rejected_proposals=len(rejected), structural_issues=len(issues),
            batches_restored=tracker.data['batches_restored'], warnings=warnings,
        )
    except BaseException as error:
        # BaseException also catches Ctrl+C, so interrupted runs are logged too.
        # The error is re-raised afterwards; main.py decides how to show it.
        tracker.finish(
            status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed',
            error=error, stage=stage,
        )
        logger.info(f'Experiment failure/interruption recorded: output/experiments/{tracker.run_id}.json')
        raise


# ---------------------------------------------------------------------------
# Batch helpers
# ---------------------------------------------------------------------------
def _restore_checkpoint(checkpoint: Path, signature: str, target_paths: list[str], index: int):
    """Saved proposals of a completed batch, or None when it must be (re)generated."""
    if not checkpoint.is_file():
        return None
    try:
        saved = read_json(checkpoint)
        # Only reuse the checkpoint if it belongs to exactly this job and batch.
        if (saved.get('signature') == signature and saved.get('targets') == target_paths
                and isinstance(saved.get('proposals'), list)):
            return saved
    except (OSError, ValueError, TypeError, AttributeError):
        logger.warning(f'Batch {index}: corrupt checkpoint; regenerating.')
    return None


def _map_batch(inputs: _Inputs, batch: list[dict], source_paths: set[str],
               model: str, tracker: ExperimentTracker) -> list[dict]:
    """Ask Gemini for one batch; retry omitted or invalid targets once."""
    target_paths = [f['path'] for f in batch]
    batch_proposals = run_gemini(
        inputs.source_fields, batch, all_target_fields=inputs.all_target_fields,
        source_documents=inputs.source_docs, historical_pairs=inputs.historical_docs,
        model=model, on_event=tracker.event,
    )
    repair = find_proposals_needing_retry(batch_proposals, batch, source_paths)
    if repair:
        logger.info(f'Gemini omitted or invalidated {len(repair)} target(s); retrying those once.')
        corrections = run_gemini(
            inputs.source_fields, repair, all_target_fields=inputs.all_target_fields,
            source_documents=inputs.source_docs, historical_pairs=inputs.historical_docs,
            model=model, on_event=tracker.event,
        )
        # Merge: corrected proposals replace the original ones for those targets.
        repair_paths = {r['path'] for r in repair}
        corrected = {p.get('target_path'): p for p in corrections
                     if isinstance(p, dict) and p.get('target_path') in repair_paths}
        original = {p.get('target_path'): p for p in batch_proposals
                    if isinstance(p, dict) and p.get('target_path') in target_paths}
        original.update(corrected)
        batch_proposals = [original[p] for p in target_paths if p in original]
    # Drop anything Gemini returned for targets that were not part of this batch.
    return [p for p in batch_proposals if isinstance(p, dict) and p.get('target_path') in target_paths]
