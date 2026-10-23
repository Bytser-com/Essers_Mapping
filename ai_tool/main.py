"""Entry point for the XML-to-mapping-proposal prototype, with resumable batches."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from excel_generator import export_excel
from mapping_validator import validate_mappings
from xml_parser import parse_xml_directory

ROOT = Path(__file__).resolve().parent


def _write_json(path, payload):
    """Write JSON atomically so an interruption cannot leave a half-written checkpoint."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(temp_path, path)


def _job_signature(sources, targets, selected_targets, verified_path, batch_size, model):
    """Identify the exact inputs/settings that produced a set of checkpoints."""
    digest = hashlib.sha256()
    settings = {
        "model": model,
        "batch_size": batch_size,
        "target_paths": [field["path"] for field in selected_targets],
    }
    digest.update(json.dumps(settings, sort_keys=True).encode("utf-8"))

    # Reuse checkpoints only when the XML files, prompt, and references are unchanged.
    inputs = sorted(
        [*sources, *targets, verified_path, ROOT / "prompt.txt", ROOT / "readprompt.py"],
        key=lambda path: str(path),
    )
    for path in inputs:
        digest.update(str(path.relative_to(ROOT)).encode("utf-8"))
        if path.is_file():
            digest.update(path.read_bytes())
        else:
            digest.update(b"<missing>")

    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(
        description="Generate proposed XML mappings into an Excel review workbook."
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="Run bundled demonstration without calling Gemini"
    )
    parser.add_argument(
        "--limit-targets", type=int, default=10,
        help="Only map first N target fields (default: 10; 0 = all)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=10,
        help="Number of target fields per Gemini call"
    )
    args = parser.parse_args()
    if args.batch_size < 1 or args.limit_targets < 0:
        parser.error("batch-size must be >= 1 and limit-targets must be >= 0")

    source_dir = ROOT / "data" / "source"
    target_dir = ROOT / "data" / "target"
    sources = sorted(source_dir.rglob("*.xml"))
    targets = sorted(target_dir.rglob("*.xml"))
    if not sources or not targets:
        raise SystemExit(
            "Place at least one source XML in data/source and one target XML in data/target."
        )

    source_inventory = parse_xml_directory(source_dir)
    target_inventory = parse_xml_directory(target_dir)

    # No DELIV_NUMB-only filter: process the selected number of target fields.
    if not source_inventory or not target_inventory:
        raise SystemExit("No XML leaf fields found in source and target directories.")
    if args.limit_targets:
        target_inventory = target_inventory[:args.limit_targets]

    print(
        f"Discovered {len(source_inventory)} source fields "
        f"and {len(target_inventory)} target fields to propose."
    )

    verified_path = ROOT / "data" / "reference" / "verified_mappings.json"
    verified = (
        json.loads(verified_path.read_text(encoding="utf-8"))
        if verified_path.exists() else []
    )

    if args.offline:
        print("OFFLINE MODE: using bundled illustrative proposals, not Gemini.")
        sample = ROOT / "data" / "reference" / "demo_proposals.json"
        proposals = json.loads(sample.read_text(encoding="utf-8"))["mappings"]
    else:
        from google.genai import errors
        from readprompt import run_gemini

        load_dotenv(ROOT / ".env")
        model = os.environ.get("GEMINI_MODEL", "")
        if not model:
            raise SystemExit("Set GEMINI_MODEL in your .env file.")

        signature = _job_signature(
            sources, targets, target_inventory, verified_path, args.batch_size, model
        )
        checkpoint_dir = ROOT / "output" / "checkpoints" / signature[:16]
        print(f"Checkpoint folder: {checkpoint_dir}")
        proposals = []

        batches = [
            target_inventory[offset:offset + args.batch_size]
            for offset in range(0, len(target_inventory), args.batch_size)
        ]
        for index, group in enumerate(batches, start=1):
            target_paths = [field["path"] for field in group]
            checkpoint_file = checkpoint_dir / f"batch_{index:04d}.json"

            if checkpoint_file.exists():
                try:
                    saved = json.loads(checkpoint_file.read_text(encoding="utf-8"))
                    if (
                        saved.get("job_signature") == signature
                        and saved.get("target_paths") == target_paths
                        and isinstance(saved.get("proposals"), list)
                    ):
                        proposals.extend(saved["proposals"])
                        print(f"Batch {index}/{len(batches)}: restored from checkpoint.")
                        continue
                except (OSError, ValueError, TypeError, AttributeError):
                    pass
                print(f"Batch {index}: checkpoint invalid; regenerating.")

            print(f"Mapping batch {index}/{len(batches)}: {len(group)} target fields")
            try:
                batch_proposals = run_gemini(source_inventory, group, verified)
            except errors.ServerError as exc:
                if exc.code == 503:
                    raise SystemExit(
                        "Gemini is overloaded (503). Earlier batches are saved. "
                        "Run the SAME command to resume."
                    ) from None
                raise
            except errors.ClientError as exc:
                if exc.code == 429:
                    raise SystemExit(
                        "Gemini rate limit exceeded (429). Earlier batches are saved. "
                        "Run the SAME command after your quota resets to resume."
                    ) from None
                raise

            if not isinstance(batch_proposals, list):
                raise SystemExit(
                    "Gemini returned an unexpected response. Earlier batches are saved; "
                    "the current batch was NOT checkpointed."
                )

            # Write the checkpoint BEFORE moving on to the next API request.
            _write_json(checkpoint_file, {
                "job_signature": signature,
                "batch_number": index,
                "target_paths": target_paths,
                "proposals": batch_proposals,
            })
            proposals.extend(batch_proposals)
            print(
                f"Batch {index}/{len(batches)} saved "
                f"({len(batch_proposals)} proposals)."
            )

    # Only generate the final package after every requested batch has completed.
    accepted, rejected, issues = validate_mappings(
        proposals, source_inventory, target_inventory
    )

    covered_targets = {mapping["target_path"] for mapping in accepted}
    for field in target_inventory:
        if field["path"] not in covered_targets:
            accepted.append({
                "source_path": "", "target_path": field["path"],
                "rule_type": "REVIEW_REQUIRED", "confidence": 0,
                "requires_review": True, "review_priority": "High",
                "reason": "No valid mapping proposal generated for this target field.",
                "evidence": "", "fixed_value": "", "transformation": "",
                "condition": "", "lookup": "", "loop": "",
                "review_question": "Which source field or business rule populates this target?",
                "risk_category": "Unmapped target", "validation_issues": [],
            })

    out = ROOT / "output"
    _write_json(out / "mapping_proposals.json", accepted)
    _write_json(out / "rejected_proposals.json", rejected)
    _write_json(out / "validation_issues.json", issues)

    output_path = export_excel(
        accepted, source_inventory, sources, targets,
        out / "mapping_package.xlsx", ROOT / "templates" / "mapping_template.xlsx"
    )
    print(f"Created: {output_path}")
    print(
        f"{len(accepted)} mapping proposals; {len(rejected)} rejected; "
        f"{len(issues)} with validation issues."
    )
    print("These are proposals requiring expert approval, not executable mappings.")


if __name__ == "__main__":
    main()
