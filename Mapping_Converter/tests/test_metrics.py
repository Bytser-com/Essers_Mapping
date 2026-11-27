"""GET /metrics (routers/metrics.py): Prometheus exposition for Mapping Converter."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import app
from services.metrics import metrics


@pytest.fixture(autouse=True)
def reset_metrics():
    metrics.reset()
    yield
    metrics.reset()


def test_converter_metrics_endpoint_exposes_prometheus_counters():
    metrics.record_approval("scheduled")
    metrics.record_ai_review("ACCEPTED", duration_seconds=2.5)
    metrics.record_ai_review("REJECTED", duration_seconds=1.5)
    metrics.record_conversion("succeeded")

    client = TestClient(app)
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    body = response.text
    assert "essers_converter_ai_reviews_active 0" in body
    assert 'essers_converter_approvals_total{outcome="scheduled"} 1' in body
    assert 'essers_converter_ai_reviews_total{decision="ACCEPTED"} 1' in body
    assert 'essers_converter_ai_reviews_total{decision="REJECTED"} 1' in body
    assert 'essers_converter_ai_reviews_total{decision="FAILED"} 0' in body
    assert "essers_converter_ai_review_duration_seconds_sum 4.000" in body
    assert "essers_converter_ai_review_duration_seconds_count 2" in body
    assert 'essers_converter_conversions_total{outcome="succeeded"} 1' in body
