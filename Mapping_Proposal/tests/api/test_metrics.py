"""GET /metrics (routers/metrics.py): Prometheus exposition for proposal health and AI runs."""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import metrics as metrics_router
from routers import upload as upload_router
from services.metrics import metrics
from services.proposals import AiStatus, ProposalStatus, ProposalStore


@pytest.fixture(autouse=True)
def reset_metrics():
    metrics.reset()
    yield
    metrics.reset()


@pytest.fixture
def incoming(tmp_path, monkeypatch):
    folder = tmp_path / 'source'
    monkeypatch.setattr(upload_router, 'incoming_dir', lambda: folder)
    monkeypatch.setattr(metrics_router, 'incoming_dir', lambda: folder)
    return folder


@pytest.fixture
def store(tmp_path):
    return ProposalStore(tmp_path / 'sftp-shared' / 'proposals')


@pytest.fixture
def client(incoming, store):
    app = FastAPI()
    app.include_router(upload_router.router)
    app.include_router(metrics_router.router)
    app.dependency_overrides[upload_router.get_proposal_store] = lambda: store
    return TestClient(app)


def test_metrics_reports_proposal_counts_and_upload_counters(client, incoming, store):
    ref_failed = store.create_proposal('Klant A', 'inbound')
    store.set_status(ref_failed, ProposalStatus.AI_GENERATING, AiStatus.FAILED, error='503')

    ref_ready = store.create_proposal('Klant B', 'outbound')
    store.set_status(ref_ready, ProposalStatus.READY_FOR_REVIEW, None)

    resp_upload = client.post(
        '/upload',
        data={'customer_name': 'Klant C', 'proposal_type': 'inbound'},
        files=[('files', ('order.xml', b'<root/>', 'text/xml'))],
    )
    assert resp_upload.status_code == 201

    resp = client.get('/metrics')
    assert resp.status_code == 200
    assert 'text/plain' in resp.headers['content-type']
    body = resp.text

    assert 'essers_proposals_sftp_up 1' in body
    assert 'essers_proposals_total 3' in body
    assert 'essers_proposals_running_total 1' in body
    assert 'essers_proposals_failed_total 1' in body
    assert 'essers_proposals_ready_for_review_total 1' in body
    assert 'essers_proposal_incoming_queue_size{state="pending"} 1' in body
    assert 'essers_proposal_uploads_total{outcome="accepted"} 1' in body
    assert 'essers_proposals_by_status{status="AI_GENERATING",ai_status="FAILED",proposal_type="inbound"} 1' in body


def test_metrics_marks_sftp_down_when_storage_fails(client, store, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError('SFTP unreachable')

    monkeypatch.setattr(store, 'list_proposals', boom)
    resp = client.get('/metrics')
    assert resp.status_code == 200
    assert 'essers_proposals_sftp_up 0' in resp.text
    assert 'essers_proposals_total 0' in resp.text


def test_metrics_counts_incoming_queue_states(client, incoming):
    pending = incoming / '20261125-100000_a_111111'
    pending.mkdir(parents=True)
    (pending / 'upload.json').write_text(json.dumps({'customer': 'A'}), encoding='utf-8')
    (incoming / '20261125-100001_b_222222.processing').mkdir(parents=True)
    (incoming / 'failed' / '20261125-090000_c_333333').mkdir(parents=True)

    resp = client.get('/metrics')
    assert resp.status_code == 200
    assert 'essers_proposal_incoming_queue_size{state="pending"} 1' in resp.text
    assert 'essers_proposal_incoming_queue_size{state="processing"} 1' in resp.text
    assert 'essers_proposal_incoming_queue_size{state="failed"} 1' in resp.text
