"""POST /upload (routers/upload.py): the uploaded files end up in the source folder in the
layout the incoming watcher expects, so the AI starts automatically.

Only the upload router is mounted, so the watcher thread of api.py does not start.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import upload as upload_router
from services.incoming_watcher import IncomingWatcher
from services.proposals import ProposalStatus, ProposalStore


@pytest.fixture
def incoming(tmp_path, monkeypatch):
    folder = tmp_path / 'source'
    monkeypatch.setattr(upload_router, 'incoming_dir', lambda: folder)
    return folder


@pytest.fixture
def client(incoming):
    app = FastAPI()
    app.include_router(upload_router.router)
    return TestClient(app)


def xml(name: str, content: bytes = b'<root />'):
    return ('files', (name, content, 'text/xml'))


def test_upload_stores_all_files_of_one_customer_together_in_the_source_folder(client, incoming):
    response = client.post('/upload', data={'customer_name': ' Ostavel '},
                           files=[xml('order_1.xml', b'<a />'), xml('order_2.xml', b'<b />')])

    assert response.status_code == 201
    body = response.json()
    assert body['customer'] == 'Ostavel'
    assert body['files'] == ['order_1.xml', 'order_2.xml']
    [folder] = list(incoming.iterdir())
    assert folder.name == body['upload_id']
    assert '_ostavel_' in folder.name
    assert sorted(p.name for p in folder.iterdir()) == ['order_1.xml', 'order_2.xml', 'upload.json']
    assert (folder / 'order_2.xml').read_bytes() == b'<b />'
    assert json.loads((folder / 'upload.json').read_text(encoding='utf-8')) == {'customer': 'Ostavel'}


def test_every_upload_gets_its_own_folder(client, incoming):
    client.post('/upload', data={'customer_name': 'Ostavel'}, files=[xml('order.xml')])
    client.post('/upload', data={'customer_name': 'Ostavel'}, files=[xml('order.xml')])

    assert len(list(incoming.iterdir())) == 2


def test_upload_without_customer_is_refused(client, incoming):
    response = client.post('/upload', data={'customer_name': '  '}, files=[xml('order.xml')])

    assert response.status_code == 400
    assert response.json()['detail'] == 'Upload mislukt: Vul eerst een klant in.'
    assert not incoming.exists()


def test_upload_with_a_file_that_is_not_xml_stores_nothing(client, incoming):
    response = client.post('/upload', data={'customer_name': 'Ostavel'},
                           files=[xml('order.xml'), ('files', ('order.pdf', b'%PDF', 'application/pdf'))])

    assert response.status_code == 400
    assert response.json()['detail'] == 'Upload mislukt: dit is geen XML-bestand.'
    assert not incoming.exists()


def test_file_name_cannot_leave_the_upload_folder(client, incoming):
    response = client.post('/upload', data={'customer_name': 'Ostavel'}, files=[xml('../../evil.xml')])

    assert response.status_code == 201
    [folder] = list(incoming.iterdir())
    assert (folder / 'evil.xml').is_file()


def test_uploaded_files_are_picked_up_by_the_watcher(client, incoming, tmp_path):
    client.post('/upload', data={'customer_name': 'Ostavel'}, files=[xml('order.xml')])
    store = ProposalStore(tmp_path / 'sftp-shared' / 'proposals')
    received = []

    def fake_ai(settings):  # stands in for the AI run: remembers which files it got
        received.append(sorted(p.name for p in settings.source_dir.glob('*.xml')))
        raise RuntimeError('stop after the hand-over')

    IncomingWatcher(incoming, store, run=fake_ai).run_once()

    assert received == [['order.xml']]
    [row] = store.list_proposals()
    assert row.customer == 'Ostavel'
    assert row.status is ProposalStatus.AI_GENERATING  # the AI run (fake) failed: "Mislukt"
