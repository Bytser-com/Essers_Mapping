"""POST /upload (routers/upload.py): the uploaded files end up in the source folder in the
layout the incoming watcher expects, so the AI starts automatically.

Before returning success, the metadata document is created on the SFTP storage.
Only the upload router is mounted, so the watcher thread of api.py does not start.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import upload as upload_router
from scripts.errors import StorageError
from services.incoming_watcher import IncomingWatcher
from services.proposals import ProposalStatus, ProposalStore


@pytest.fixture
def incoming(tmp_path, monkeypatch):
    folder = tmp_path / 'source'
    monkeypatch.setattr(upload_router, 'incoming_dir', lambda: folder)
    return folder


@pytest.fixture
def store(tmp_path):
    return ProposalStore(tmp_path / 'sftp-shared' / 'proposals')


@pytest.fixture
def client(incoming, store):
    app = FastAPI()
    app.include_router(upload_router.router)
    app.dependency_overrides[upload_router.get_proposal_store] = lambda: store
    return TestClient(app)


def xml(name: str, content: bytes = b'<root />'):
    return ('files', (name, content, 'text/xml'))


def test_upload_stores_all_files_of_one_customer_together_in_the_source_folder(client, incoming, store):
    response = client.post('/upload', data={'customer_name': ' Ostavel ', 'proposal_type': 'inbound'},
                           files=[xml('order_1.xml', b'<a />'), xml('order_2.xml', b'<b />')])

    assert response.status_code == 201
    body = response.json()
    assert body['customer'] == 'Ostavel'
    assert body['proposal_type'] == 'inbound'
    assert body['files'] == ['order_1.xml', 'order_2.xml']
    [folder] = list(incoming.iterdir())
    assert folder.name == body['upload_id']
    assert '_ostavel_' in folder.name
    assert sorted(p.name for p in folder.iterdir()) == ['order_1.xml', 'order_2.xml', 'proposal_ref.json', 'upload.json']
    assert (folder / 'order_2.xml').read_bytes() == b'<b />'
    assert json.loads((folder / 'upload.json').read_text(encoding='utf-8')) == {
        'customer': 'Ostavel',
        'proposal_type': 'inbound',
    }
    ref_data = json.loads((folder / 'proposal_ref.json').read_text(encoding='utf-8'))
    assert ref_data['customer'] == 'Ostavel'
    assert ref_data['proposal_type'] == 'inbound'
    assert ref_data['folder'] == 'ostavel/v1/inbound'

    # The metadata document is created on SFTP right away
    [prop] = store.list_proposals()
    assert prop.customer == 'Ostavel'
    assert prop.version == 1
    assert prop.proposal_type == 'inbound'
    assert prop.status is ProposalStatus.AI_GENERATING
    assert (store.root / 'ostavel' / 'v1' / 'inbound' / 'proposal.json').is_file()


def test_every_upload_gets_its_own_folder(client, incoming):
    resp1 = client.post('/upload', data={'customer_name': 'Ostavel', 'proposal_type': 'inbound'}, files=[xml('order.xml')])
    assert resp1.status_code == 201
    resp2 = client.post('/upload', data={'customer_name': 'Brunos', 'proposal_type': 'outbound'}, files=[xml('order.xml')])
    assert resp2.status_code == 201

    assert len(list(incoming.iterdir())) == 2


def test_upload_rejected_if_company_already_has_active_proposal(client, incoming):
    resp1 = client.post('/upload', data={'customer_name': 'Ostavel', 'proposal_type': 'inbound'}, files=[xml('order.xml')])
    assert resp1.status_code == 201

    resp2 = client.post('/upload', data={'customer_name': 'Ostavel', 'proposal_type': 'outbound'}, files=[xml('order.xml')])
    assert resp2.status_code == 400
    assert 'al een voorstel actief' in resp2.json()['detail']

    # Case-insensitive check also rejects
    resp3 = client.post('/upload', data={'customer_name': 'ostavel', 'proposal_type': 'inbound'}, files=[xml('order.xml')])
    assert resp3.status_code == 400
    assert 'al een voorstel actief' in resp3.json()['detail']


def test_upload_without_customer_is_refused(client, incoming):
    response = client.post('/upload', data={'customer_name': '  ', 'proposal_type': 'inbound'}, files=[xml('order.xml')])

    assert response.status_code == 400
    assert response.json()['detail'] == 'Upload mislukt: Vul eerst een klant in.'
    assert not incoming.exists()


@pytest.mark.parametrize('bad_type', ['', '   ', None])
def test_upload_without_proposal_type_is_refused(client, incoming, bad_type):
    data = {'customer_name': 'Ostavel'}
    if bad_type is not None:
        data['proposal_type'] = bad_type
    response = client.post('/upload', data=data, files=[xml('order.xml')])

    assert response.status_code == 400
    detail = response.json()['detail']
    assert 'proposal_type' in detail
    assert 'verplicht' in detail or 'required' in detail
    assert not incoming.exists()


@pytest.mark.parametrize('prop_type', ['inbound', 'outbound', 'inboud-accept'])
def test_upload_with_different_proposal_types(client, incoming, prop_type):
    response = client.post('/upload', data={'customer_name': 'Ostavel', 'proposal_type': prop_type},
                           files=[xml('order.xml')])

    assert response.status_code == 201
    assert response.json()['proposal_type'] == prop_type
    [folder] = list(incoming.iterdir())
    data = json.loads((folder / 'upload.json').read_text(encoding='utf-8'))
    assert data['proposal_type'] == prop_type


def test_upload_converts_proposal_type_to_lowercase(client, incoming):
    response = client.post('/upload', data={'customer_name': 'Ostavel', 'proposal_type': 'INBOUND'},
                           files=[xml('order.xml')])

    assert response.status_code == 201
    assert response.json()['proposal_type'] == 'inbound'
    [folder] = list(incoming.iterdir())
    data = json.loads((folder / 'upload.json').read_text(encoding='utf-8'))
    assert data['proposal_type'] == 'inbound'


def test_upload_with_a_file_that_is_not_xml_stores_nothing(client, incoming):
    response = client.post('/upload', data={'customer_name': 'Ostavel', 'proposal_type': 'inbound'},
                           files=[xml('order.xml'), ('files', ('order.pdf', b'%PDF', 'application/pdf'))])

    assert response.status_code == 400
    assert response.json()['detail'] == 'Upload mislukt: dit is geen XML-bestand.'
    assert not incoming.exists()


def test_file_name_cannot_leave_the_upload_folder(client, incoming):
    response = client.post('/upload', data={'customer_name': 'Ostavel', 'proposal_type': 'inbound'},
                           files=[xml('../../evil.xml')])

    assert response.status_code == 201
    [folder] = list(incoming.iterdir())
    assert (folder / 'evil.xml').is_file()


def test_uploaded_files_are_picked_up_by_the_watcher(client, incoming, store):
    client.post('/upload', data={'customer_name': 'Ostavel', 'proposal_type': 'inbound'}, files=[xml('order.xml')])
    received = []

    def fake_ai(settings):  # stands in for the AI run: remembers which files it got
        received.append(sorted(p.name for p in settings.source_dir.glob('*.xml')))
        raise RuntimeError('stop after the hand-over')

    IncomingWatcher(incoming, store, run=fake_ai).run_once()

    assert received == [['order.xml']]
    [row] = store.list_proposals()
    assert row.customer == 'Ostavel'
    assert row.proposal_type == 'inbound'
    assert row.version == 1  # reused version 1; did not create version 2
    assert row.status is ProposalStatus.AI_GENERATING  # the AI run (fake) failed: "Mislukt"
    assert (store.root / 'ostavel' / 'v1' / 'inbound' / 'proposal.json').is_file()


def test_upload_fails_when_sftp_storage_fails(client, incoming, store, monkeypatch):
    def failing_create(customer, proposal_type='inbound', created_by='Analist A'):
        raise StorageError('Cannot connect to SFTP sftp-shared:22')

    monkeypatch.setattr(store, 'create_proposal', failing_create)
    response = client.post('/upload', data={'customer_name': 'Ostavel', 'proposal_type': 'inbound'}, files=[xml('order.xml')])

    assert response.status_code == 500
    assert 'Upload mislukt: kan metadata niet opslaan op SFTP server' in response.json()['detail']
    assert not incoming.exists() or list(incoming.iterdir()) == []


def test_watcher_reuses_existing_proposal_from_api_upload(client, incoming, store):
    response = client.post('/upload', data={'customer_name': 'Ostavel', 'proposal_type': 'inbound'}, files=[xml('order.xml')])
    assert response.status_code == 201

    # Initially on SFTP: version 1 created
    proposals = store.list_proposals()
    assert len(proposals) == 1
    assert proposals[0].version == 1
    assert proposals[0].proposal_type == 'inbound'

    # Watcher processes the upload
    watcher = IncomingWatcher(incoming, store, run=lambda s: None)
    watcher.run_once()

    # Still only 1 version exists on SFTP; watcher reused version 1
    proposals_after = store.list_proposals()
    assert len(proposals_after) == 1
    assert proposals_after[0].version == 1
    assert proposals_after[0].proposal_type == 'inbound'


def test_upload_creates_version_based_on_existing_packages(client, tmp_path, store):
    # Setup /Packages/Nouryon/v3
    pkg_v3 = tmp_path / 'sftp-shared' / 'packages' / 'Nouryon' / 'v3'
    pkg_v3.mkdir(parents=True)

    response = client.post('/upload', data={'customer_name': 'Nouryon', 'proposal_type': 'inbound'}, files=[xml('order.xml')])
    assert response.status_code == 201

    proposals = store.list_proposals()
    assert len(proposals) == 1
    assert proposals[0].customer == 'Nouryon'
    assert proposals[0].version == 4
    assert proposals[0].proposal_type == 'inbound'
    assert proposals[0].id == 'nouryon/v4/inbound'


def test_ai_retry_recovers_failed_uploads(client, incoming, store, monkeypatch):
    from services.proposals import AiStatus

    triggered = []
    monkeypatch.setattr(upload_router, 'trigger_watcher_retry', lambda s: triggered.append(s))

    # Create a proposal in store that failed
    ref = store.create_proposal('Ostavel', 'inbound')
    store.set_status(ref, ProposalStatus.AI_GENERATING, AiStatus.FAILED, error='Gemini failed')

    # Create a failed upload directory in incoming/failed
    failed_dir = incoming / 'failed' / '20261120-120000_ostavel_abc123'
    failed_dir.mkdir(parents=True)
    (failed_dir / 'order.xml').write_text('<root/>', encoding='utf-8')
    (failed_dir / 'upload.json').write_text(json.dumps({'customer': 'Ostavel', 'proposal_type': 'inbound'}), encoding='utf-8')
    (failed_dir / 'proposal_ref.json').write_text(
        json.dumps({'customer': 'Ostavel', 'version': ref.version, 'folder': ref.folder, 'proposal_type': 'inbound'}),
        encoding='utf-8',
    )
    (failed_dir / 'error.txt').write_text('Some error', encoding='utf-8')

    response = client.post('/ai-retry')
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'ok'
    assert data['retried_count'] >= 1

    # Verify failed folder was moved back to incoming
    assert not failed_dir.exists()
    restored = list(incoming.glob('*ostavel*'))
    assert len(restored) == 1
    assert (restored[0] / 'order.xml').is_file()
    assert not (restored[0] / 'error.txt').exists()

    # Verify proposal status reset to RUNNING
    [p] = store.list_proposals()
    assert p.ai_status is AiStatus.RUNNING
    assert len(triggered) == 1


def test_ai_retry_resets_stuck_proposal_in_store_without_failed_dir(client, store):
    from services.proposals import AiStatus

    ref = store.create_proposal('Brunos', 'outbound')
    store.set_status(ref, ProposalStatus.AI_GENERATING, AiStatus.FAILED, error='Gemini 503')

    response = client.post('/ai-retry')
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'ok'
    assert data['retried_count'] == 1

    [p] = store.list_proposals()
    assert p.ai_status is AiStatus.RUNNING

