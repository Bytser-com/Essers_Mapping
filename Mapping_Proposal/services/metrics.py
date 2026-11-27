"""Lightweight, zero-dependency Prometheus metrics for the Mapping Proposal service.

Exposes:
- In-process counters and durations for uploads, AI runs, and retries.
- Cached snapshot gauges of active proposals on shared SFTP storage (grouped by
  workflow status, AI status, and proposal type), oldest running AI job age,
  SFTP reachability, and local incoming queue depth.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from services.proposals import AiStatus, ProposalStatus, ProposalStore

logger = logging.getLogger(__name__)

_PROMETHEUS_CONTENT_TYPE = 'text/plain; version=0.0.4; charset=utf-8'
_CACHE_TTL_SECONDS = 10.0

_UPLOAD_OUTCOMES = ('accepted', 'rejected_validation', 'rejected_active', 'error')
_AI_RUN_OUTCOMES = ('succeeded', 'failed', 'retrying')


class ProposalMetricsCollector:
    """Thread-safe in-memory metrics registry for Mapping_Proposal."""

    def __init__(self, cache_ttl_seconds: float = _CACHE_TTL_SECONDS) -> None:
        self._lock = threading.Lock()
        self._cache_ttl_seconds = cache_ttl_seconds
        self._uploads: Counter[str] = Counter()
        self._ai_runs: Counter[str] = Counter()
        self._ai_duration_sum = 0.0
        self._ai_duration_count = 0
        self._ai_retries = 0
        self._snapshot_at = 0.0
        self._snapshot_cache: dict | None = None

    def reset(self) -> None:
        """Reset all counters and clear cached SFTP snapshots (used in tests)."""
        with self._lock:
            self._uploads.clear()
            self._ai_runs.clear()
            self._ai_duration_sum = 0.0
            self._ai_duration_count = 0
            self._ai_retries = 0
            self._snapshot_at = 0.0
            self._snapshot_cache = None

    def invalidate_cache(self) -> None:
        with self._lock:
            self._snapshot_at = 0.0
            self._snapshot_cache = None

    def record_upload(self, outcome: str) -> None:
        with self._lock:
            self._uploads[outcome] += 1
            self._snapshot_at = 0.0

    def record_ai_run(self, outcome: str, duration_seconds: float | None = None) -> None:
        with self._lock:
            self._ai_runs[outcome] += 1
            if duration_seconds is not None and duration_seconds >= 0:
                self._ai_duration_sum += float(duration_seconds)
                self._ai_duration_count += 1
            self._snapshot_at = 0.0

    def record_retry(self, retried_count: int) -> None:
        if retried_count <= 0:
            return
        with self._lock:
            self._ai_retries += int(retried_count)
            self._snapshot_at = 0.0

    def _collect_storage_snapshot(self, store: ProposalStore) -> dict:
        now_monotonic = time.monotonic()
        with self._lock:
            if (
                self._snapshot_cache is not None
                and (now_monotonic - self._snapshot_at) < self._cache_ttl_seconds
            ):
                return self._snapshot_cache

        snapshot: dict = {
            'sftp_up': 1,
            'total': 0,
            'running': 0,
            'failed': 0,
            'ready_for_review': 0,
            'in_review': 0,
            'ai_checking_review': 0,
            'returned': 0,
            'oldest_running_age_seconds': 0.0,
            'by_status': Counter(),
        }
        try:
            proposals = store.list_proposals()
            now_utc = datetime.now(UTC)
            snapshot['total'] = len(proposals)
            for item in proposals:
                status_val = item.status.value
                ai_val = item.ai_status.value if item.ai_status else 'NONE'
                prop_type = item.proposal_type or 'unknown'
                snapshot['by_status'][(status_val, ai_val, prop_type)] += 1

                if item.ai_status is AiStatus.RUNNING:
                    snapshot['running'] += 1
                    age = max(0.0, (now_utc - item.uploaded_at.astimezone(UTC)).total_seconds())
                    if age > snapshot['oldest_running_age_seconds']:
                        snapshot['oldest_running_age_seconds'] = age
                elif item.ai_status is AiStatus.FAILED:
                    snapshot['failed'] += 1

                if item.status is ProposalStatus.READY_FOR_REVIEW:
                    snapshot['ready_for_review'] += 1
                elif item.status is ProposalStatus.IN_REVIEW:
                    snapshot['in_review'] += 1
                elif item.status is ProposalStatus.AI_CHECKING_REVIEW:
                    snapshot['ai_checking_review'] += 1
                elif item.status is ProposalStatus.RETURNED:
                    snapshot['returned'] += 1
        except Exception as error:
            logger.warning('Failed to read proposal snapshot for /metrics: %s', error)
            snapshot['sftp_up'] = 0

        with self._lock:
            self._snapshot_cache = snapshot
            self._snapshot_at = time.monotonic()
        return snapshot

    @staticmethod
    def _collect_queue_counts(incoming_dir: Path) -> dict[str, int]:
        counts = {'pending': 0, 'processing': 0, 'failed': 0}
        if not incoming_dir.is_dir():
            return counts
        try:
            for entry in incoming_dir.iterdir():
                if not entry.is_dir():
                    continue
                if entry.name == 'failed':
                    counts['failed'] = sum(1 for child in entry.iterdir() if child.is_dir())
                elif entry.name == 'processed':
                    continue
                elif entry.name.endswith('.processing'):
                    counts['processing'] += 1
                elif (entry / 'upload.json').is_file():
                    counts['pending'] += 1
        except OSError as error:
            logger.warning('Failed to inspect incoming queue directory %s: %s', incoming_dir, error)
        return counts

    def render(self, store: ProposalStore, incoming_dir: Path) -> str:
        """Render all metrics in Prometheus text exposition format (0.0.4)."""
        snapshot = self._collect_storage_snapshot(store)
        queue = self._collect_queue_counts(incoming_dir)

        with self._lock:
            uploads = dict(self._uploads)
            ai_runs = dict(self._ai_runs)
            ai_duration_sum = self._ai_duration_sum
            ai_duration_count = self._ai_duration_count
            ai_retries = self._ai_retries

        lines: list[str] = [
            '# HELP essers_proposals_sftp_up Whether Mapping_Proposal can read proposals from shared SFTP storage (1=up, 0=down).',
            '# TYPE essers_proposals_sftp_up gauge',
            f'essers_proposals_sftp_up {snapshot["sftp_up"]}',
            '# HELP essers_proposals_total Total active mapping proposals visible on shared SFTP storage.',
            '# TYPE essers_proposals_total gauge',
            f'essers_proposals_total {snapshot["total"]}',
            '# HELP essers_proposals_running_total Number of proposals currently being generated by AI (ai_status=RUNNING).',
            '# TYPE essers_proposals_running_total gauge',
            f'essers_proposals_running_total {snapshot["running"]}',
            '# HELP essers_proposals_failed_total Number of proposals whose AI step failed (ai_status=FAILED).',
            '# TYPE essers_proposals_failed_total gauge',
            f'essers_proposals_failed_total {snapshot["failed"]}',
            '# HELP essers_proposals_ready_for_review_total Number of proposals ready for analyst review.',
            '# TYPE essers_proposals_ready_for_review_total gauge',
            f'essers_proposals_ready_for_review_total {snapshot["ready_for_review"]}',
            '# HELP essers_proposals_in_review_total Number of proposals currently in analyst review.',
            '# TYPE essers_proposals_in_review_total gauge',
            f'essers_proposals_in_review_total {snapshot["in_review"]}',
            '# HELP essers_proposals_ai_checking_review_total Number of proposals awaiting AI review check.',
            '# TYPE essers_proposals_ai_checking_review_total gauge',
            f'essers_proposals_ai_checking_review_total {snapshot["ai_checking_review"]}',
            '# HELP essers_proposals_returned_total Number of proposals returned/rejected by AI review.',
            '# TYPE essers_proposals_returned_total gauge',
            f'essers_proposals_returned_total {snapshot["returned"]}',
            '# HELP essers_proposals_oldest_running_age_seconds Age in seconds of the oldest RUNNING proposal (0 when none running).',
            '# TYPE essers_proposals_oldest_running_age_seconds gauge',
            f'essers_proposals_oldest_running_age_seconds {snapshot["oldest_running_age_seconds"]:.1f}',
            '# HELP essers_proposals_by_status Active proposals grouped by workflow status, AI status, and proposal type.',
            '# TYPE essers_proposals_by_status gauge',
        ]
        for (status_val, ai_val, prop_type), count in sorted(snapshot['by_status'].items()):
            lines.append(
                f'essers_proposals_by_status{{status="{_escape_label(status_val)}",'
                f'ai_status="{_escape_label(ai_val)}",'
                f'proposal_type="{_escape_label(prop_type)}"}} {count}'
            )

        lines.extend([
            '# HELP essers_proposal_incoming_queue_size Local incoming upload queue folders by state.',
            '# TYPE essers_proposal_incoming_queue_size gauge',
        ])
        for state in ('pending', 'processing', 'failed'):
            lines.append(f'essers_proposal_incoming_queue_size{{state="{state}"}} {queue[state]}')

        lines.extend([
            '# HELP essers_proposal_uploads_total Total POST /upload requests handled by outcome.',
            '# TYPE essers_proposal_uploads_total counter',
        ])
        for outcome in _UPLOAD_OUTCOMES:
            lines.append(f'essers_proposal_uploads_total{{outcome="{outcome}"}} {uploads.get(outcome, 0)}')
        for outcome, count in sorted(uploads.items()):
            if outcome not in _UPLOAD_OUTCOMES:
                lines.append(f'essers_proposal_uploads_total{{outcome="{_escape_label(outcome)}"}} {count}')

        lines.extend([
            '# HELP essers_proposal_ai_runs_total Total AI proposal generation runs by outcome.',
            '# TYPE essers_proposal_ai_runs_total counter',
        ])
        for outcome in _AI_RUN_OUTCOMES:
            lines.append(f'essers_proposal_ai_runs_total{{outcome="{outcome}"}} {ai_runs.get(outcome, 0)}')

        lines.extend([
            '# HELP essers_proposal_ai_run_duration_seconds_sum Cumulative duration of AI proposal generation runs in seconds.',
            '# TYPE essers_proposal_ai_run_duration_seconds_sum counter',
            f'essers_proposal_ai_run_duration_seconds_sum {ai_duration_sum:.3f}',
            '# HELP essers_proposal_ai_run_duration_seconds_count Number of timed AI proposal generation runs.',
            '# TYPE essers_proposal_ai_run_duration_seconds_count counter',
            f'essers_proposal_ai_run_duration_seconds_count {ai_duration_count}',
            '# HELP essers_proposal_ai_retries_total Total failed proposals requeued via POST /ai-retry.',
            '# TYPE essers_proposal_ai_retries_total counter',
            f'essers_proposal_ai_retries_total {ai_retries}',
        ])
        return '\n'.join(lines) + '\n'


def _escape_label(value: str) -> str:
    return value.replace('\\', '\\\\').replace('\n', '\\n').replace('"', '\\"')


PROMETHEUS_CONTENT_TYPE = _PROMETHEUS_CONTENT_TYPE
metrics = ProposalMetricsCollector()
