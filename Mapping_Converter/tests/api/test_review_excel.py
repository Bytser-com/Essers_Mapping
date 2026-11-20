"""POST /review-excel: AI consistency review of a stored proposal workbook (story 51).

Gemini is never called: scripts.pipeline.review_with_gemini is replaced by a fake.
"""
import json

import pytest
from fastapi.testclient import TestClient

from api import app
from routers import approve as approve_router
from scripts.errors import StorageError
from scripts.gemini_review import ReviewUnavailable
from services.storage import LocalStorage

URL = '/review-excel?company=nouryon&version=v2&proposalType=inbound'


@pytest.fixture
def client(proposals_root):
    app.dependency_overrides[approve_router.get_proposal_storage] = lambda: LocalStorage(proposals_root)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def stored_proposal(proposals_root, mapping_workbook):
    """nouryon/v2/inbound with metadata and a valid workbook; returns the folder."""
    folder = proposals_root / 'nouryon' / 'v2' / 'inbound'
    folder.mkdir(parents=True)
    (folder / 'metadata.json').write_text(json.dumps({'filename': 'MProposal-Nouryon_V2.xlsx'}), encoding='utf-8')
    (folder / 'MProposal-Nouryon_V2.xlsx').write_bytes(mapping_workbook())
    return folder


def fake_review(decision, findings=()):
    def review(rows):
        return {'decision': decision, 'summary': 'test', 'findings': list(findings), 'checked_mappings': len(rows)}
    return review


def test_accepted_review_returns_200(client, stored_proposal, monkeypatch):
    monkeypatch.setattr('scripts.pipeline.review_with_gemini', fake_review('ACCEPTED'))

    response = client.post(URL)

    assert response.status_code == 200
    assert response.json()['decision'] == 'ACCEPTED'
    assert response.json()['checked_mappings'] == 1


def test_rejected_review_returns_200_with_findings(client, stored_proposal, monkeypatch):
    monkeypatch.setattr('scripts.pipeline.review_with_gemini', fake_review('REJECTED', ['Row 3: no source']))

    response = client.post(URL)

    assert response.status_code == 200
    assert response.json()['decision'] == 'REJECTED'
    assert response.json()['findings'] == ['Row 3: no source']


def test_version_without_prefix_is_accepted(client, stored_proposal, monkeypatch):
    monkeypatch.setattr('scripts.pipeline.review_with_gemini', fake_review('ACCEPTED'))
    response = client.post('/review-excel?company=Nouryon&version=2&proposalType=INBOUND')
    assert response.status_code == 200


def test_hidden_alias_review(client, stored_proposal, monkeypatch):
    monkeypatch.setattr('scripts.pipeline.review_with_gemini', fake_review('ACCEPTED'))
    assert client.post('/review?company=nouryon&version=v2&proposalType=inbound').status_code == 200


@pytest.mark.parametrize('query', [
    '',
    '?version=v2&proposalType=inbound',
    '?company=nouryon&proposalType=inbound',
    '?company=nouryon&version=v2',
    '?company=%20&version=v2&proposalType=inbound',
    '?company=nouryon&version=latest&proposalType=inbound',
])
def test_invalid_parameters_return_400(client, query):
    response = client.post(f'/review-excel{query}')
    assert response.status_code == 400
    assert response.json()['detail']


def test_unknown_proposal_returns_404(client, proposals_root):
    assert client.post(URL).status_code == 404


def test_missing_workbook_returns_404(client, stored_proposal):
    (stored_proposal / 'MProposal-Nouryon_V2.xlsx').unlink()
    response = client.post(URL)
    assert response.status_code == 404
    assert 'Excel' in response.json()['detail']


def test_corrupt_workbook_returns_422(client, stored_proposal):
    (stored_proposal / 'MProposal-Nouryon_V2.xlsx').write_bytes(b'not an excel')
    assert client.post(URL).status_code == 422


def test_storage_error_returns_502_without_details(client, monkeypatch):
    def broken(*args, **kwargs):
        raise StorageError('Cannot connect to SFTP sftp-shared:22 as secret-user')

    monkeypatch.setattr('routers.review.load_proposal_workbook', broken)
    response = client.post(URL)

    assert response.status_code == 502
    assert 'secret-user' not in response.json()['detail']


@pytest.mark.parametrize('error', [ReviewUnavailable('quota exceeded'), RuntimeError('boom')])
def test_review_failure_returns_503_and_never_accepts(client, stored_proposal, monkeypatch, error):
    def unavailable(rows):
        raise error

    monkeypatch.setattr('scripts.pipeline.review_with_gemini', unavailable)
    response = client.post(URL)

    assert response.status_code == 503
    assert response.json()['detail'] == 'De AI-controle is tijdelijk niet beschikbaar'
