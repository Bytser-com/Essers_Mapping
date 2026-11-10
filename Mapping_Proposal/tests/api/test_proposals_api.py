"""GET /proposals (routers/proposals.py): the endpoint behind the proposals overview on Home.

Only the proposals router is mounted, with a store on a temporary folder, so neither the
upload watcher nor the SFTP server is needed. Every test name starts with its Jira test
case (TC-57-xx).
"""
from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from routers import proposals as proposals_router
from scripts.errors import StorageError
from services.proposals import ProposalStore


def write_proposal(root, folder, version, customer, uploaded_at, status='READY_FOR_REVIEW', ai_status=None):
    version_dir = root / folder / f'v{version}'
    version_dir.mkdir(parents=True)
    (version_dir / 'proposal.json').write_text(json.dumps({
        'customer': customer, 'uploaded_at': uploaded_at, 'status': status, 'ai_status': ai_status,
    }), encoding='utf-8')


@pytest.fixture
def root(tmp_path):
    return tmp_path / 'proposals'


@pytest.fixture
def client(root):
    app = FastAPI()
    app.include_router(proposals_router.router)
    app.dependency_overrides[proposals_router.get_proposal_store] = lambda: ProposalStore(root)
    return TestClient(app)


def test_tc_57_02_get_proposals_returns_total_and_rows_newest_first(root, client):
    write_proposal(root, 'voorbeeldbedrijf-a', 1, 'Voorbeeldbedrijf A', '2026-10-22T14:05:00+02:00',
                   'AI_GENERATING', 'RUNNING')
    write_proposal(root, 'voorbeeldbedrijf-b', 2, 'Voorbeeldbedrijf B', '2026-10-21T10:30:00+02:00')

    response = client.get('/proposals')

    assert response.status_code == 200
    body = response.json()
    assert body['total'] == 2
    assert [p['customer'] for p in body['proposals']] == ['Voorbeeldbedrijf A', 'Voorbeeldbedrijf B']
    first = body['proposals'][0]
    assert first['id'] == 'voorbeeldbedrijf-a/v1'
    assert first['version'] == 1
    assert first['status'] == 'AI_GENERATING'
    assert first['ai_status'] == 'RUNNING'
    assert first['can_open'] is False
    assert first['uploaded_at'].startswith('2026-10-22T14:05:00')
    assert body['proposals'][1]['ai_status'] is None
    assert body['proposals'][1]['can_open'] is True


def test_tc_57_02_only_the_latest_version_per_customer_by_default(root, client):
    write_proposal(root, 'ostavel', 1, 'Ostavel', '2026-10-20T10:00:00+02:00')
    write_proposal(root, 'ostavel', 2, 'Ostavel', '2026-10-21T10:00:00+02:00')

    body = client.get('/proposals').json()

    assert body['total'] == 1
    assert [p['version'] for p in body['proposals']] == [2]


def test_tc_57_02_all_versions_parameter_returns_every_version(root, client):
    write_proposal(root, 'ostavel', 1, 'Ostavel', '2026-10-20T10:00:00+02:00')
    write_proposal(root, 'ostavel', 2, 'Ostavel', '2026-10-21T10:00:00+02:00')

    body = client.get('/proposals', params={'all_versions': 'true'}).json()

    assert body['total'] == 2
    assert [p['version'] for p in body['proposals']] == [2, 1]


def test_tc_57_09_no_proposals_gives_an_empty_list(client):
    response = client.get('/proposals')

    assert response.status_code == 200
    assert response.json() == {'total': 0, 'proposals': []}


def test_tc_57_10_unreachable_sftp_server_gives_503(client):
    class UnreachableStore:
        def list_proposals(self, *, all_versions=False):
            raise StorageError('Cannot connect to SFTP sftp-shared:22')

    client.app.dependency_overrides[proposals_router.get_proposal_store] = lambda: UnreachableStore()

    response = client.get('/proposals')

    assert response.status_code == 503
    assert 'sftp-shared' in response.json()['detail']


def test_tc_57_01_invalid_all_versions_value_is_refused(client):
    assert client.get('/proposals', params={'all_versions': 'misschien'}).status_code == 422


def test_tc_57_02_store_dependency_uses_the_configured_storage(monkeypatch, tmp_path):
    monkeypatch.setenv('SFTP_SHARED_HOST', '')  # no SFTP server: local folder
    store = proposals_router.get_proposal_store()

    assert isinstance(store, ProposalStore)
    assert str(store.root).replace('\\', '/').endswith('data/sftp-shared/proposals')
