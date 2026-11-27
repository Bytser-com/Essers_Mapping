import json

import pytest
from fastapi.testclient import TestClient

from api import app
from routers import approve as approve_router
from scripts.errors import StorageError
from services.storage import LocalStorage

URL = '/approve?company=nouryon&version=v1&proposalType=inbound'


@pytest.fixture
def started(monkeypatch):
    """Records the background AI reviews instead of running them."""
    calls = []
    monkeypatch.setattr(approve_router, 'trigger_ai_review', lambda *args: calls.append(args))
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


@pytest.mark.parametrize('description', ['', '   '])
def test_empty_description_is_optional_and_returns_200(client, proposals_root, description):
    write_metadata(proposals_root)
    response = client.post(URL, json={'description': description})
    assert response.status_code == 200
    assert response.json()['status'] == 'AI_CHECKING_REVIEW'


def test_too_long_description_returns_400(client, proposals_root):
    write_metadata(proposals_root)
    response = client.post(URL, json={'description': 'a' * 201})
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
    assert isinstance(approve_router.get_packages_storage(), LocalStorage)


def test_ai_retry_restarts_stuck_proposals(client, proposals_root, monkeypatch):
    # Setup stuck proposal
    folder = proposals_root / 'nouryon' / 'v1' / 'inbound'
    folder.mkdir(parents=True, exist_ok=True)
    meta_path = folder / 'metadata.json'
    meta_path.write_text(json.dumps({
        'customer': 'Nouryon',
        'status': 'AI_CHECKING_REVIEW',
        'ai_status': 'FAILED',
        'ai_review_error': 'Gemini 503 error',
    }), encoding='utf-8')

    triggered = []
    monkeypatch.setattr(
        approve_router, 'trigger_ai_review',
        lambda storage, comp, ver, pt, packages: triggered.append((comp, ver, pt)),
    )

    response = client.post('/ai-retry')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'ok'
    assert body['retried_count'] == 1
    assert body['retried_proposals'] == [{
        'company': 'nouryon',
        'version': 'v1',
        'proposal_type': 'inbound',
    }]

    # Check metadata updated
    updated_meta = json.loads(meta_path.read_text(encoding='utf-8'))
    assert updated_meta['ai_status'] == 'RUNNING'
    assert 'ai_review_error' not in updated_meta
    assert len(triggered) == 1
    assert triggered[0] == ('nouryon', 'v1', 'inbound')


def test_ai_retry_no_stuck_proposals(client, proposals_root):
    # Setup proposal not in AI_CHECKING_REVIEW
    folder = proposals_root / 'nouryon' / 'v1' / 'inbound'
    folder.mkdir(parents=True, exist_ok=True)
    meta_path = folder / 'metadata.json'
    meta_path.write_text(json.dumps({
        'customer': 'Nouryon',
        'status': 'READY_FOR_REVIEW',
        'ai_status': None,
    }), encoding='utf-8')

    response = client.post('/ai-retry')
    assert response.status_code == 200
    body = response.json()
    assert body['retried_count'] == 0
    assert body['retried_proposals'] == []


# ---------------------------------------------------------------------------
# Story 187: after approving, the AI review runs in the background
# ---------------------------------------------------------------------------
def test_approve_starts_the_ai_review_in_the_background(client, proposals_root, started):
    write_metadata(proposals_root)

    assert client.post(URL, json={'description': 'Ok'}).status_code == 200

    assert len(started) == 1
    proposals, company, version, proposal_type, packages = started[0]
    assert isinstance(proposals, LocalStorage)
    assert isinstance(packages, LocalStorage)
    assert (company, version, proposal_type) == ('nouryon', 'v1', 'inbound')


def test_failed_approval_starts_nothing(client, started):
    assert client.post(URL, json={'description': 'Ok'}).status_code == 404
    assert started == []


def run_approve_end_to_end(proposals_root, packages_root, mapping_excel, monkeypatch, review):
    """approve -> background task (TestClient runs it) -> AI review replaced by ``review``."""
    path = write_metadata(proposals_root)
    (path.parent / 'MProposal-Nouryon_V1.xlsx').write_bytes(mapping_excel)
    monkeypatch.setattr('scripts.pipeline.review_with_gemini', review)
    app.dependency_overrides[approve_router.get_proposal_storage] = lambda: LocalStorage(proposals_root)
    app.dependency_overrides[approve_router.get_packages_storage] = lambda: LocalStorage(packages_root)
    try:
        response = TestClient(app).post(URL, json={'description': 'Eerste versie'})
    finally:
        app.dependency_overrides.clear()
    assert response.json()['status'] == 'AI_CHECKING_REVIEW'  # the analyst gets an answer straight away
    return json.loads(path.read_text(encoding='utf-8'))


def test_accepted_review_publishes_the_package(proposals_root, packages_root, mapping_excel, monkeypatch):
    data = run_approve_end_to_end(proposals_root, packages_root, mapping_excel, monkeypatch, lambda _rows: {
        'decision': 'ACCEPTED', 'summary': 'Consistent', 'findings': [], 'checked_mappings': 1,
    })

    assert data['status'] == 'APPROVED'
    package = json.loads((packages_root / 'nouryon' / 'v1' / 'inbound' / 'MPackage.json').read_text(encoding='utf-8'))
    assert package['meta']['description'] == 'Eerste versie'
    active = json.loads((packages_root / 'nouryon' / 'active.json').read_text(encoding='utf-8'))
    assert active['inbound']['version'] == 'v1'


def test_rejected_review_returns_the_proposal(proposals_root, packages_root, mapping_excel, monkeypatch):
    data = run_approve_end_to_end(proposals_root, packages_root, mapping_excel, monkeypatch, lambda _rows: {
        'decision': 'REJECTED', 'summary': 'Conflict', 'findings': ['Rij 3: dubbel doelveld'], 'checked_mappings': 1,
    })

    assert data['status'] == 'RETURNED'
    assert data['ai_status'] == 'FAILED'
    assert data['ai_review']['findings'] == ['Rij 3: dubbel doelveld']
    assert list(packages_root.iterdir()) == []


def test_unavailable_review_can_be_retried(proposals_root, packages_root, mapping_excel, monkeypatch):
    from scripts.gemini_review import ReviewUnavailable

    def unavailable(_rows):
        raise ReviewUnavailable('Gemini 503')

    data = run_approve_end_to_end(proposals_root, packages_root, mapping_excel, monkeypatch, unavailable)

    assert data['status'] == 'AI_CHECKING_REVIEW'  # picked up again by POST /ai-retry
    assert data['ai_status'] == 'FAILED'
    assert 'Gemini 503' in data['ai_review_error']
    assert list(packages_root.iterdir()) == []
