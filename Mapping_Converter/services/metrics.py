"""Lightweight, zero-dependency Prometheus metrics for the Mapping Converter service.

Exposes counters and durations for proposal approvals, AI review decisions,
and Excel-to-JSON mapping package conversions.
"""
from __future__ import annotations

import threading
from collections import Counter

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

_APPROVAL_OUTCOMES = ("scheduled", "invalid", "not_found", "conflict", "error")
_REVIEW_DECISIONS = ("ACCEPTED", "REJECTED", "FAILED")
_CONVERSION_OUTCOMES = ("succeeded", "invalid", "error")


class ConverterMetricsCollector:
    """Thread-safe in-memory metrics registry for Mapping_Converter."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._approvals: Counter[str] = Counter()
        self._reviews: Counter[str] = Counter()
        self._conversions: Counter[str] = Counter()
        self._review_duration_sum = 0.0
        self._review_duration_count = 0

    def reset(self) -> None:
        with self._lock:
            self._approvals.clear()
            self._reviews.clear()
            self._conversions.clear()
            self._review_duration_sum = 0.0
            self._review_duration_count = 0

    def record_approval(self, outcome: str) -> None:
        with self._lock:
            self._approvals[outcome] += 1

    def record_ai_review(self, decision: str, duration_seconds: float | None = None) -> None:
        normalized = (decision or "FAILED").strip().upper()
        with self._lock:
            self._reviews[normalized] += 1
            if duration_seconds is not None and duration_seconds >= 0:
                self._review_duration_sum += float(duration_seconds)
                self._review_duration_count += 1

    def record_conversion(self, outcome: str) -> None:
        with self._lock:
            self._conversions[outcome] += 1

    def render(self, active_reviews: int = 0) -> str:
        with self._lock:
            approvals = dict(self._approvals)
            reviews = dict(self._reviews)
            conversions = dict(self._conversions)
            review_duration_sum = self._review_duration_sum
            review_duration_count = self._review_duration_count

        lines: list[str] = [
            "# HELP essers_converter_ai_reviews_active Number of AI reviews currently running in Mapping_Converter.",
            "# TYPE essers_converter_ai_reviews_active gauge",
            f"essers_converter_ai_reviews_active {max(0, int(active_reviews))}",
            "# HELP essers_converter_approvals_total Total POST /approve requests by outcome.",
            "# TYPE essers_converter_approvals_total counter",
        ]
        for outcome in _APPROVAL_OUTCOMES:
            lines.append(f'essers_converter_approvals_total{{outcome="{outcome}"}} {approvals.get(outcome, 0)}')

        lines.extend([
            "# HELP essers_converter_ai_reviews_total Total AI review executions by decision (ACCEPTED, REJECTED, FAILED).",
            "# TYPE essers_converter_ai_reviews_total counter",
        ])
        for decision in _REVIEW_DECISIONS:
            lines.append(f'essers_converter_ai_reviews_total{{decision="{decision}"}} {reviews.get(decision, 0)}')
        for decision, count in sorted(reviews.items()):
            if decision not in _REVIEW_DECISIONS:
                lines.append(f'essers_converter_ai_reviews_total{{decision="{_escape_label(decision)}"}} {count}')

        lines.extend([
            "# HELP essers_converter_ai_review_duration_seconds_sum Cumulative duration of AI review executions in seconds.",
            "# TYPE essers_converter_ai_review_duration_seconds_sum counter",
            f"essers_converter_ai_review_duration_seconds_sum {review_duration_sum:.3f}",
            "# HELP essers_converter_ai_review_duration_seconds_count Number of timed AI review executions.",
            "# TYPE essers_converter_ai_review_duration_seconds_count counter",
            f"essers_converter_ai_review_duration_seconds_count {review_duration_count}",
            "# HELP essers_converter_conversions_total Total Excel-to-JSON mapping package conversions by outcome.",
            "# TYPE essers_converter_conversions_total counter",
        ])
        for outcome in _CONVERSION_OUTCOMES:
            lines.append(f'essers_converter_conversions_total{{outcome="{outcome}"}} {conversions.get(outcome, 0)}')

        return "\n".join(lines) + "\n"


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


metrics = ConverterMetricsCollector()
