import io
import json

import openpyxl
import pytest
from fastapi.testclient import TestClient

from api import app
from routers import approve as approve_router
from scripts.errors import StorageError
from services.storage import LocalStorage

URL = '/approve?company=nouryon&version=v1&proposalType=inbound'


def make_proposal_workbook():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Mapping Proposal'
    ws.append(['Category'])
    ws.append(['Target segment path', 'Target field name', 'Source full path'])
    ws.append(['/DEST/HEADER', 'DOC_NUM', '/SRC/HEADER/NUMBER'])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def client(proposals_root):
    app.dependency_overrides[approve_router.get_proposal_storage] = lambda: LocalStorage(proposals_root)
    yield TestClient(app)
    app.dependency_overrides.clear()


def write_metadata(root, status='In review', filename='proposal.xlsx'):
    folder = root / 'nouryon' / 'v1' / 'inbound'
    folder.mkdir(parents=True, exist_ok=True)
    if filename:
        (folder / filename).write_bytes(make_proposal_workbook())
    path = folder / 'metadata.json'
    path.write_text(json.dumps({'customer': 'Nouryon', 'status': status, 'filename': filename}), encoding='utf-8')
    return path


def test_approve_returns_200_and_updates_status(client, proposals_root, monkeypatch):
    monkeypatch.setattr('scripts.pipeline.run_review', lambda contents: {
        'decision': 'ACCEPTED',
        'summary': 'All mappings look consistent',
        'findings': [],
    })
    write_metadata(proposals_root)

    response = client.post(URL, json={'description': 'Eerste versie voor Nouryon'})

    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'ACCEPTED'
    assert body['decision'] == 'ACCEPTED'
    assert body['approval_description'] == 'Eerste versie voor Nouryon'


@pytest.mark.parametrize('description', ['', '   '])
def test_empty_description_is_optional_and_returns_200(client, proposals_root, description, monkeypatch):
    monkeypatch.setattr('scripts.pipeline.run_review', lambda contents: {
        'decision': 'ACCEPTED',
        'summary': 'All mappings look consistent',
        'findings': [],
    })
    write_metadata(proposals_root)
    response = client.post(URL, json={'description': description})
    assert response.status_code == 200
    assert response.json()['status'] == 'ACCEPTED'


def test_approve_rejected_returns_422(client, proposals_root, monkeypatch):
    monkeypatch.setattr('scripts.pipeline.run_review', lambda contents: {
        'decision': 'REJECTED',
        'summary': 'Tegenstrijdige mappings gevonden',
        'findings': ['Veld X conflicteert met veld Y'],
    })
    write_metadata(proposals_root)
    response = client.post(URL, json={'description': 'Test'})
    assert response.status_code == 422
    assert 'Tegenstrijdige mappings gevonden' in response.json()['detail']


def test_approve_ai_failure_returns_502(client, proposals_root, monkeypatch):
    monkeypatch.setattr(approve_router, 'trigger_ai_review', lambda *args, **kwargs: None)
    write_metadata(proposals_root)
    response = client.post(URL, json={'description': 'Test'})
    assert response.status_code == 502
    assert 'AI-controle kon niet worden voltooid' in response.json()['detail']


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
    write_metadata(proposals_root, status='AI_CHECKING_REVIEW')
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
    monkeypatch.setattr(approve_router, 'trigger_ai_review', lambda storage, comp, ver, pt: triggered.append((comp, ver, pt)))

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


def test_trigger_ai_review_accepted_converts_and_saves_package(proposals_root, tmp_path, monkeypatch):
    packages_root = tmp_path / 'packages'
    monkeypatch.setattr(approve_router, 'get_packages_storage', lambda: LocalStorage(packages_root))

    storage = LocalStorage(proposals_root)
    folder = proposals_root / 'nouryon' / 'v1' / 'inbound'
    folder.mkdir(parents=True, exist_ok=True)
    excel_file = folder / 'proposal.xlsx'
    excel_file.write_bytes(make_proposal_workbook())

    meta_file = folder / 'proposal.json'
    meta_file.write_text(json.dumps({
        'customer': 'nouryon',
        'version': 'v1',
        'proposal_type': 'inbound',
        'status': 'AI_CHECKING_REVIEW',
        'filename': 'proposal.xlsx',
        'uploadUser': 'test_analyst',
    }), encoding='utf-8')

    monkeypatch.setattr('scripts.pipeline.run_review', lambda contents: {
        'decision': 'ACCEPTED',
        'summary': 'All mappings look consistent',
        'findings': [],
    })

    result = approve_router.trigger_ai_review(storage, 'nouryon', 'v1', 'inbound')
    assert result['decision'] == 'ACCEPTED'

    # Verify package is saved on packages storage
    pkg_file = packages_root / 'nouryon' / 'v1' / 'inbound' / 'MPackage.json'
    assert pkg_file.exists()
    pkg_data = json.loads(pkg_file.read_text(encoding='utf-8'))
    assert len(pkg_data['mappings']) == 1
    assert pkg_data['mappings'][0]['target_path'] == '/DEST/HEADER/DOC_NUM'
    assert pkg_data['mappings'][0]['source_path'] == '/SRC/HEADER/NUMBER'

    # Verify proposal files are removed from proposals storage after conversion
    assert not excel_file.exists()
    assert not meta_file.exists()
    assert not (proposals_root / 'nouryon').exists()


def test_trigger_ai_review_accepted_preserves_other_proposal_types(proposals_root, tmp_path, monkeypatch):
    packages_root = tmp_path / 'packages'
    monkeypatch.setattr(approve_router, 'get_packages_storage', lambda: LocalStorage(packages_root))

    storage = LocalStorage(proposals_root)
    # Create inbound proposal
    inbound_folder = proposals_root / 'nouryon' / 'v1' / 'inbound'
    inbound_folder.mkdir(parents=True, exist_ok=True)
    (inbound_folder / 'proposal.xlsx').write_bytes(make_proposal_workbook())
    (inbound_folder / 'proposal.json').write_text(json.dumps({
        'customer': 'nouryon',
        'version': 'v1',
        'proposal_type': 'inbound',
        'status': 'AI_CHECKING_REVIEW',
        'filename': 'proposal.xlsx',
        'uploadUser': 'test_analyst',
    }), encoding='utf-8')

    # Create outbound proposal for same company
    outbound_folder = proposals_root / 'nouryon' / 'v1' / 'outbound'
    outbound_folder.mkdir(parents=True, exist_ok=True)
    outbound_excel = outbound_folder / 'proposal.xlsx'
    outbound_excel.write_bytes(make_proposal_workbook())
    outbound_meta = outbound_folder / 'proposal.json'
    outbound_meta.write_text(json.dumps({
        'customer': 'nouryon',
        'version': 'v1',
        'proposal_type': 'outbound',
        'status': 'READY_FOR_REVIEW',
        'filename': 'proposal.xlsx',
    }), encoding='utf-8')

    monkeypatch.setattr('scripts.pipeline.run_review', lambda contents: {
        'decision': 'ACCEPTED',
        'summary': 'All mappings look consistent',
        'findings': [],
    })

    result = approve_router.trigger_ai_review(storage, 'nouryon', 'v1', 'inbound')
    assert result['decision'] == 'ACCEPTED'

    # Package created for inbound
    pkg_file = packages_root / 'nouryon' / 'v1' / 'inbound' / 'MPackage.json'
    assert pkg_file.exists()

    # Inbound deleted
    assert not inbound_folder.exists()

    # Outbound preserved
    assert outbound_folder.exists()
    assert outbound_excel.exists()
    assert outbound_meta.exists()


def test_trigger_ai_review_rejected_does_not_convert_or_save_package(proposals_root, tmp_path, monkeypatch):
    packages_root = tmp_path / 'packages'
    monkeypatch.setattr(approve_router, 'get_packages_storage', lambda: LocalStorage(packages_root))

    storage = LocalStorage(proposals_root)
    folder = proposals_root / 'nouryon' / 'v1' / 'inbound'
    folder.mkdir(parents=True, exist_ok=True)
    excel_file = folder / 'proposal.xlsx'
    excel_file.write_bytes(make_proposal_workbook())

    meta_file = folder / 'proposal.json'
    meta_file.write_text(json.dumps({
        'customer': 'nouryon',
        'version': 'v1',
        'proposal_type': 'inbound',
        'status': 'AI_CHECKING_REVIEW',
        'filename': 'proposal.xlsx',
        'uploadUser': 'test_analyst',
    }), encoding='utf-8')

    monkeypatch.setattr('scripts.pipeline.run_review', lambda contents: {
        'decision': 'REJECTED',
        'summary': 'Inconsistent mappings found',
        'findings': ['Invalid source path mapping'],
    })

    result = approve_router.trigger_ai_review(storage, 'nouryon', 'v1', 'inbound')
    assert result['decision'] == 'REJECTED'

    # Verify package was NOT created
    pkg_file = packages_root / 'nouryon' / 'v1' / 'inbound' / 'MPackage.json'
    assert not pkg_file.exists()

    # Verify proposal files are NOT removed
    assert excel_file.exists()
    assert meta_file.exists()

    # Verify metadata marked RETURNED and FAILED
    updated_meta = json.loads(meta_file.read_text(encoding='utf-8'))
    assert updated_meta['status'] == 'RETURNED'
    assert updated_meta['ai_status'] == 'FAILED'
    assert 'package_path' not in updated_meta

