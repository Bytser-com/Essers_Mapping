"""Prometheus metrics endpoint (GET /metrics) for Mapping Proposal."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from routers.upload import get_proposal_store
from scripts.config import incoming_dir
from services.metrics import PROMETHEUS_CONTENT_TYPE, metrics
from services.proposals import ProposalStore

router = APIRouter()


@router.get('/metrics', include_in_schema=False)
def prometheus_metrics(store: ProposalStore = Depends(get_proposal_store)) -> Response:
    payload = metrics.render(store, incoming_dir())
    return Response(content=payload, media_type=PROMETHEUS_CONTENT_TYPE)
