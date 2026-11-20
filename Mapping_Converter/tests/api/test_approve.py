import json

import pytest
from fastapi.testclient import TestClient

from api import app
from routers import approve as approve_router
from scripts.errors import StorageError
from services.storage import LocalStorage

URL = '/approve?company=nouryon&version=v1&proposalType=inbound'


@pytest.fixture
def packages_root(tmp_path):
    root = tmp_path / 'packages'
    root.mkdir()
    return root


@pytest.fixture
def started(monkeypatch):
    """Records the background tasks instead of running the AI review."""
    calls = []
    monkeypatch.setattr(approve_router, 'finalize_in_background', lambda *args: calls.append(args))
    return calls


@pytest.fixture
def client(proposals_root, packages_root, started):
    app.dependency_overrides[approve_router.get_proposal_storage] = lambda: LocalStorage(proposals_root)
    app.dependency_overrides[approve_router.get_packages_storage] = lambda: LocalStorage(packages_root)
    yield TestClient(app)
    app.dependency_overrides.clear()


def write_metadata(root, status='In review'):
    folder = root / 'nouryon' / 'v1' / 'inbound'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'metadata.json'
    path.write_text(json.dumps({'customer': 'Nouryon', 'status': status}), encoding='utf-8')
    return path


def test_approve_returns_200_and_updates_status(client, proposals_root):
    path = write_metadata(proposals_root)

    response = client.post(URL, json={'description': 'Eerste versie voor Nouryon'})

    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'AI_CHECKING_REVIEW'
    assert body['approval_description'] == 'Eerste versie voor Nouryon'
    assert json.loads(path.read_text(encoding='utf-8'))['status'] == 'AI_CHECKING_REVIEW'


@pytest.mark.parametrize('description', ['', '   ', 'a' * 201])
def test_invalid_description_returns_400(client, proposals_root, description):
    write_metadata(proposals_root)
    response = client.post(URL, json={'description': description})
    assert response.status_code == 400
    assert response.json()['detail']


def test_missing_proposal_type_returns_400(client, proposals_root):
    write_metadata(proposals_root)
    response = client.post('/approve?company=nouryon&version=v1', json={'description': 'Ok'})
    assert response.status_code == 400
    assert 'Proposaltype' in response.json()['detail']


def test_unknown_proposal_returns_404(client):
    response = client.post(URL, json={'description': 'Ok'})
    assert response.status_code == 404


def test_approving_twice_returns_409(client, proposals_root):
    write_metadata(proposals_root)
    assert client.post(URL, json={'description': 'Eerste'}).status_code == 200

    response = client.post(URL, json={'description': 'Tweede'})

    assert response.status_code == 409
    assert 'AI-controle is al bezig' in response.json()['detail']


def test_storage_error_returns_502(client, monkeypatch):
    def broken(*args, **kwargs):
        raise StorageError('Cannot connect to SFTP')

    monkeypatch.setattr(approve_router, 'approve_proposal', broken)
    response = client.post(URL, json={'description': 'Ok'})

    assert response.status_code == 502
    assert response.json()['detail'] == 'De bestanden zijn tijdelijk niet bereikbaar'


def test_storage_dependency_uses_the_configured_storage(monkeypatch):
    monkeypatch.setenv('SFTP_SHARED_HOST', '')
    assert isinstance(approve_router.get_proposal_storage(), LocalStorage)


# ---------------------------------------------------------------------------
# Story 187: after approving, the AI review starts in the background
# ---------------------------------------------------------------------------
def test_approve_starts_the_ai_review_in_the_background(client, proposals_root, started):
    write_metadata(proposals_root)

    assert client.post(URL, json={'description': 'Ok'}).status_code == 200

    assert len(started) == 1
    proposals, packages, company, version, proposal_type = started[0]
    assert isinstance(proposals, LocalStorage)
    assert isinstance(packages, LocalStorage)
    assert (company, version, proposal_type) == ('nouryon', 'v1', 'inbound')


def test_failed_approval_starts_nothing(client, started):
    assert client.post(URL, json={'description': 'Ok'}).status_code == 404
    assert started == []


def test_background_review_updates_the_proposal(proposals_root, packages_root, mapping_workbook, monkeypatch):
    """End to end without Gemini: approve -> background task -> RETURNED with the findings."""
    path = write_metadata(proposals_root)
    (path.parent / 'MProposal-Nouryon_V1.xlsx').write_bytes(mapping_workbook())
    monkeypatch.setattr('scripts.pipeline.review_with_gemini', lambda rows: {
        'decision': 'REJECTED', 'summary': 'Conflict', 'findings': ['Rij 3: dubbel doelveld'], 'checked_mappings': 1,
    })
    app.dependency_overrides[approve_router.get_proposal_storage] = lambda: LocalStorage(proposals_root)
    app.dependency_overrides[approve_router.get_packages_storage] = lambda: LocalStorage(packages_root)
    try:
        response = TestClient(app).post(URL, json={'description': 'Ok'})  # TestClient runs background tasks
    finally:
        app.dependency_overrides.clear()

    assert response.json()['status'] == 'AI_CHECKING_REVIEW'  # the analyst gets an answer straight away
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['status'] == 'RETURNED'
    assert data['ai_review']['findings'] == ['Rij 3: dubbel doelveld']
