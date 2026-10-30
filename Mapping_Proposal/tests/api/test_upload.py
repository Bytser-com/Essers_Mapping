"""API tests for /upload and /customers endpoints."""
from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from Mapping_Proposal.api import app
from Mapping_Proposal.scripts.config import SFTPSettings

client = TestClient(app)


def test_upload_missing_customer():
    response = client.post(
        '/upload',
        data={'customer_name': ''},
        files={'file': ('order.xml', b'<root/>', 'application/xml')},
    )
    assert response.status_code == 400
    assert 'Vul eerst een klant in.' in response.json()['detail']


def test_upload_invalid_file_extension():
    response = client.post(
        '/upload',
        data={'customer_name': 'Ostavel'},
        files={'file': ('order.pdf', b'%PDF', 'application/pdf')},
    )
    assert response.status_code == 400
    assert 'Upload mislukt: dit is geen XML-bestand.' in response.json()['detail']


def test_upload_success_and_customer_listing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    storage_dir = tmp_path / 'sftp_storage'
    source_dir = tmp_path / 'source'
    monkeypatch.setattr('Mapping_Proposal.scripts.storage.SFTP_STORAGE_DIR', storage_dir)
    monkeypatch.setattr('Mapping_Proposal.routers.upload.SOURCE_DIR', source_dir)

    # Perform upload
    response = client.post(
        '/upload',
        data={'customer_name': 'Ostavel Logistics'},
        files={'file': ('shipment_001.xml', b'<shipment id="1"/>', 'application/xml')},
    )
    assert response.status_code == 201
    json_data = response.json()
    assert json_data['file_name'] == 'shipment_001.xml'
    assert json_data['customer_name'] == 'Ostavel Logistics'
    assert (storage_dir / 'Ostavel Logistics' / 'shipment_001.xml').exists()
    assert (source_dir / 'shipment_001.xml').exists()

    # Get customers list
    cust_response = client.get('/customers')
    assert cust_response.status_code == 200
    assert cust_response.json() == {'customers': ['Ostavel Logistics']}
