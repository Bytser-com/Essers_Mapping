"""Local experiment log with durable, per-job token accounting.

Each invocation has its own global CSV/JSON record. In addition, a small
``usage_ledger.json`` under the run folder retains API-reported usage immediately,
including when a later batch errors and the command must be resumed.

No raw XML, prompts, responses, or API credentials are written to this ledger.
"""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import time
from uuid import uuid4

TOKEN_FIELDS = ('input_tokens', 'output_tokens', 'total_tokens')
COUNTER_FIELDS = ('api_attempts', 'api_retries', 'api_errors')
METRIC_FIELDS = (*TOKEN_FIELDS, *COUNTER_FIELDS, 'usage_reports')

COLUMNS = [
    'run_id', 'started_utc', 'finished_utc', 'status', 'model',
    'dataset_version', 'prompt_sha256', 'code_version',
    'history_pairs_per_company', 'historical_pairs_sent',
    'source_samples_requested', 'source_samples_sent',
    'target_segment', 'targets_requested', 'batch_size', 'batches_total',
    'batches_restored', 'api_attempts', 'api_retries', 'api_errors',
    # These three represent the whole job (including previous invocations).
    'input_tokens', 'output_tokens', 'total_tokens',
    # Per-invocation usage, for diagnostics and transparent reporting.
    'execution_input_tokens', 'execution_output_tokens', 'execution_total_tokens',
    'job_api_attempts', 'job_api_retries', 'job_api_errors',
    'duration_seconds', 'job_active_duration_seconds',
    'token_accounting_complete', 'token_accounting_note',
    'mapping_rows', 'placeholders', 'rejected_proposals', 'structural_issues',
    'historical_evidence_checked', 'historical_evidence_rejected',
    'expert_review_status', 'expert_correct', 'expert_partial',
    'expert_incorrect', 'expert_unverifiable', 'expert_acceptance_rate',
    'workbook_path', 'run_folder',
    'error_stage', 'error_type', 'error_code',
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _zero_metrics() -> dict:
    return {name: 0 for name in METRIC_FIELDS}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(temp, path)


class ExperimentTracker:
    """Tracks one CLI execution and cumulative usage of its resumable job."""

    def __init__(self, *, settings: dict, run_dir: Path, root: Path,
                 job_signature: str = '', started_monotonic: float | None = None,
                 started_utc: str | None = None):
        self.started = started_monotonic if started_monotonic is not None else time.perf_counter()
        self.run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_' + uuid4().hex[:8]
        self.run_dir, self.root = run_dir, root
        self.data = {
            **{column: '' for column in COLUMNS}, **settings,
            'run_id': self.run_id,
            'started_utc': started_utc or utc_now(),
            'status': 'running',
            'batches_restored': 0,
            'api_attempts': 0, 'api_retries': 0, 'api_errors': 0,
            'expert_review_status': 'pending',
            'run_folder': run_dir.relative_to(root).as_posix(),
        }
        self.execution_tokens = {name: 0 for name in TOKEN_FIELDS}
        self.last_api_code = ''
        self.current_batch: str | None = None
        self.ledger_path = run_dir / 'usage_ledger.json'
        if self.ledger_path.is_file():
            self.ledger = json.loads(self.ledger_path.read_text(encoding='utf-8'))
            if self.ledger.get('signature') != job_signature:
                raise ValueError('Existing usage ledger belongs to a different job signature.')
        else:
            self.ledger = {
                'signature': job_signature, 'totals': _zero_metrics(),
                'by_batch': {}, 'job_active_duration_seconds': 0.0,
                'accounting_complete': True,
            }
        self.ledger.setdefault('totals', _zero_metrics())
        self.ledger.setdefault('by_batch', {})
        self.ledger.setdefault('accounting_complete', True)
        self.ledger.setdefault('job_active_duration_seconds', 0.0)

    def begin_batch(self, index: int) -> None:
        self.current_batch = str(index)

    def _batch_record(self, index: str | None = None) -> dict:
        key = index or self.current_batch
        if key is None:
            raise RuntimeError('A batch index must be set before recording Gemini usage.')
        return self.ledger['by_batch'].setdefault(str(key), _zero_metrics())

    def event(self, event: dict) -> None:
        """Record Gemini events immediately, so an interrupted batch is not lost."""
        kind = event.get('type')
        if kind == 'attempt':
            changes = {'api_attempts': 1}
        elif kind == 'retry':
            changes = {'api_retries': 1}
        elif kind == 'api_error':
            changes = {'api_errors': 1}
            self.last_api_code = str(event.get('code') or '')
        elif kind == 'usage':
            changes = {'usage_reports': 1}
            for name in TOKEN_FIELDS:
                try:
                    changes[name] = max(0, int(event.get(name) or 0))
                except (TypeError, ValueError):
                    changes[name] = 0
                self.execution_tokens[name] += changes[name]
        else:
            return
        batch_metrics = self._batch_record()
        for name, amount in changes.items():
            batch_metrics[name] += amount
            self.ledger['totals'][name] += amount
            if name in COUNTER_FIELDS:
                self.data[name] += amount
        _write_json(self.ledger_path, self.ledger)

    def batch_metrics(self, index: int) -> dict:
        """Snapshot for the checkpoint, including API retries/repair requests."""
        return dict(self._batch_record(str(index)))

    def restored_batch(self, index: int, metrics: dict | None = None) -> None:
        """Restore checkpoint metadata when the per-run usage ledger is missing."""
        self.data['batches_restored'] += 1
        key = str(index)
        if key not in self.ledger['by_batch']:
            if not isinstance(metrics, dict):
                # Legacy checkpoints have proposals but no token usage at all.
                self.ledger['accounting_complete'] = False
            else:
                cleaned = _zero_metrics()
                for name in METRIC_FIELDS:
                    try:
                        cleaned[name] = max(0, int(metrics.get(name) or 0))
                    except (ValueError, TypeError):
                        self.ledger['accounting_complete'] = False
                self.ledger['by_batch'][key] = cleaned
                for name, amount in cleaned.items():
                    self.ledger['totals'][name] += amount
        _write_json(self.ledger_path, self.ledger)

    def finish(self, *, status: str, results: dict | None = None,
               error: BaseException | None = None, stage: str = '') -> dict:
        self.data.update(results or {})
        self.data['status'] = status
        self.data['finished_utc'] = utc_now()
        seconds = round(time.perf_counter() - self.started, 2)
        self.data['duration_seconds'] = seconds
        self.ledger['job_active_duration_seconds'] += seconds
        self.data['job_active_duration_seconds'] = round(self.ledger['job_active_duration_seconds'], 2)
        self.data.update({name: self.ledger['totals'].get(name, 0) for name in TOKEN_FIELDS})
        self.data.update({'execution_' + name: self.execution_tokens[name] for name in TOKEN_FIELDS})
        self.data.update({'job_' + name: self.ledger['totals'].get(name, 0) for name in COUNTER_FIELDS})
        self.data['token_accounting_complete'] = bool(self.ledger['accounting_complete'])
        self.data['token_accounting_note'] = (
            'API-reported usage across the job, including resumed runs. '
            'Calls that fail without usage metadata cannot be measured; '
            'legacy checkpoints without metrics make the total incomplete.'
        )
        if error is not None:
            self.data['expert_review_status'] = ''
            self.data['error_stage'] = stage
            self.data['error_type'] = type(error).__name__
            self.data['error_code'] = self.last_api_code or (
                str(getattr(error, 'code', ''))
                if isinstance(getattr(error, 'code', None), int) else ''
            )
        _write_json(self.ledger_path, self.ledger)
        output_dir = self.root / 'output'
        _write_json(output_dir / 'experiments' / (self.run_id + '.json'), self.data)
        self._append_csv(output_dir / 'experiments.csv')
        return self.data

    def _append_csv(self, csv_path: Path) -> None:
        """Upgrade an older experiment CSV without breaking its column alignment."""
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        if csv_path.is_file() and csv_path.stat().st_size:
            with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
                reader = csv.DictReader(handle)
                previous_columns = reader.fieldnames or []
                needs_migration = previous_columns != COLUMNS
                rows = list(reader) if needs_migration else []
            # The source CSV must be closed before os.replace on Windows.
            if needs_migration:
                tmp = csv_path.with_suffix('.csv.tmp')
                with tmp.open('w', encoding='utf-8-sig', newline='') as out:
                    writer = csv.DictWriter(out, fieldnames=COLUMNS, extrasaction='ignore')
                    writer.writeheader()
                    writer.writerows(rows)
                os.replace(tmp, csv_path)
        header = not csv_path.is_file() or csv_path.stat().st_size == 0
        with csv_path.open('a', encoding='utf-8-sig' if header else 'utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction='ignore')
            if header:
                writer.writeheader()
            writer.writerow(self.data)
