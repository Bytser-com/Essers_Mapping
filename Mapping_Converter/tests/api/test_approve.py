import json

import pytest
from fastapi.testclient import TestClient

from api import app
from routers import approve as approve_router
from scripts.errors import StorageError
from services.storage import LocalStorage

URL = '/approve?company=nouryon&version=v1&proposalType=inbound'


@pytest.fixture
def client(proposals_root):
    app.dependency_overrides[approve_router.get_proposal_storage] = lambda: LocalStorage(proposals_root)
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
