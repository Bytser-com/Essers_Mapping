"""Prometheus metrics endpoint (GET /metrics) for Mapping Converter."""
from __future__ import annotations

from fastapi import APIRouter, Response

from routers import approve
from services.metrics import PROMETHEUS_CONTENT_TYPE, metrics

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
def prometheus_metrics() -> Response:
    payload = metrics.render(active_reviews=len(approve._active_reviews))
    return Response(content=payload, media_type=PROMETHEUS_CONTENT_TYPE)
