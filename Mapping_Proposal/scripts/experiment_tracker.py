"""Lightweight, local experiment log (CSV + JSON); no external tracking service.

Every invocation has its own record, even when existing checkpoints are reused.
No API keys, raw XML, prompts, or response contents are written to the log.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
import time
from uuid import uuid4


COLUMNS = [
    'run_id', 'started_utc', 'finished_utc', 'status', 'model',
    'dataset_version', 'prompt_sha256', 'code_version',
    'history_pairs_per_company', 'historical_pairs_sent',
    'source_samples_requested', 'source_samples_sent',
    'target_segment', 'targets_requested', 'batch_size', 'batches_total',
    'batches_restored', 'api_attempts', 'api_retries', 'api_errors',
    'input_tokens', 'output_tokens', 'total_tokens', 'duration_seconds',
    'mapping_rows', 'placeholders', 'rejected_proposals', 'structural_issues',
    'expert_review_status', 'expert_correct', 'expert_partial',
    'expert_incorrect', 'expert_unverifiable', 'expert_acceptance_rate',
    'workbook_path', 'run_folder',
    'error_stage', 'error_type', 'error_code',
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class ExperimentTracker:
    """Capture run settings and Gemini usage while the existing workflow runs."""

    def __init__(self, *, settings: dict, run_dir: Path, root: Path,
                 started_monotonic: float | None = None, started_utc: str | None = None):
        self.started = started_monotonic if started_monotonic is not None else time.perf_counter()
        self.run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_' + uuid4().hex[:8]
        self.run_dir = run_dir
        self.root = root
        self.data = {
            **{column: '' for column in COLUMNS},
            **settings,
            'run_id': self.run_id,
            'started_utc': started_utc or utc_now(),
            'status': 'running',
            'batches_restored': 0,
            'api_attempts': 0,
            'api_retries': 0,
            'api_errors': 0,
            'expert_review_status': 'pending',
            'run_folder': str(run_dir.relative_to(root).as_posix()),
        }
        self.usage_reports = 0
        self.tokens = {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}
        self.last_api_code = ''

    def event(self, event: dict) -> None:
        """Receive optional events from the Gemini API helper."""
        kind = event.get('type')
        if kind == 'attempt':
            self.data['api_attempts'] += 1
        elif kind == 'retry':
            self.data['api_retries'] += 1
        elif kind == 'api_error':
            self.data['api_errors'] += 1
            self.last_api_code = str(event.get('code') or '')
        elif kind == 'usage':
            self.usage_reports += 1
            for field in self.tokens:
                value = event.get(field)
                if value is not None:
                    self.tokens[field] += int(value)

    def restored_batch(self) -> None:
        self.data['batches_restored'] += 1

    def finish(self, *, status: str, results: dict | None = None,
               error: BaseException | None = None, stage: str = '') -> dict:
        self.data.update(results or {})
        self.data['status'] = status
        self.data['finished_utc'] = utc_now()
        self.data['duration_seconds'] = round(time.perf_counter() - self.started, 2)
        if self.usage_reports:
            self.data.update(self.tokens)
        if error is not None:
            self.data['expert_review_status'] = ''
            self.data['error_stage'] = stage
            self.data['error_type'] = type(error).__name__
            self.data['error_code'] = self.last_api_code or (
                str(getattr(error, 'code', '')) if isinstance(getattr(error, 'code', None), int) else ''
            )
        # Keep the central experiment history independent from mapping run artifacts.
        # The record includes run_folder/workbook_path to link back to the outputs.
        output_dir = self.root / 'output'
        save_experiment_json(output_dir / 'experiments' / (self.run_id + '.json'), self.data)
        csv_path = output_dir / 'experiments.csv'
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        needs_header = not csv_path.exists() or csv_path.stat().st_size == 0
        with csv_path.open('a', encoding='utf-8-sig' if needs_header else 'utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction='ignore')
            if needs_header:
                writer.writeheader()
            writer.writerow(self.data)
        return self.data


def save_experiment_json(path: Path, record: dict) -> None:
    """Atomic JSON sidecar so each invocation is individually inspectable."""
    import json
    import os
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(temp, path)
