import io
import json

import openpyxl
import pytest
from fastapi.testclient import TestClient

from api import app
from routers import convert as convert_router
from scripts.errors import StorageError
from services.storage import LocalStorage

XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def proposal_xlsx():
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
def packages_root(tmp_path):
    return tmp_path / 'packages'


@pytest.fixture
def client(packages_root, monkeypatch):
    monkeypatch.setenv('SFTP_SHARED_PACKAGES_DIR', '/Packages')
    app.dependency_overrides[convert_router.get_packages_storage] = lambda: LocalStorage(packages_root)
    yield TestClient(app)
    app.dependency_overrides.clear()


FORM = {'company': 'Nouryon', 'version': 'v4', 'proposal_type': 'outbound',
        'user_created': 'analist_a', 'package_version': '1.0.0'}


def test_root(client):
    response = client.get('/')
    assert response.status_code == 200
    assert 'Mapping Converter' in response.json()['message']


def test_convert_valid_excel_upload(client):
    response = client.post('/convert', files={'file': ('proposal.xlsx', proposal_xlsx(), XLSX)})

    assert response.status_code == 200
    assert response.json()['mappings'] == [{'source_path': '/SRC/HEADER/NUMBER', 'target_path': '/DEST/HEADER/DOC_NUM'}]


@pytest.mark.parametrize(('filename', 'content', 'detail'), [
    ('data.txt', b'plain text', 'Only Excel files'),
    ('empty.xlsx', b'', 'empty'),
    ('corrupt.xlsx', b'not a zip or excel', 'Failed to parse Excel workbook'),
])
def test_convert_rejects_unusable_files(client, filename, content, detail):
    response = client.post('/convert', files={'file': (filename, content, XLSX)})
    assert response.status_code == 400
    assert detail in response.json()['detail']


def test_convert_and_upload_stores_the_package(client, packages_root):
    response = client.post('/convert-and-upload', files={'file': ('proposal.xlsx', proposal_xlsx(), XLSX)}, data=FORM)

    assert response.status_code == 201
    body = response.json()
    assert body['status'] == 'success'
    assert body['sftp_path'] == '/Packages/nouryon/v4/outbound/MPackage.json'
    assert (body['company'], body['version'], body['proposal_type']) == ('nouryon', 'v4', 'outbound')
    assert body['mapping_count'] == 1
    assert body['package']['meta']['package_version'] == '1.0.0'
    stored = json.loads((packages_root / 'nouryon/v4/outbound/MPackage.json').read_text(encoding='utf-8'))
    assert stored['mappings'][0]['target_path'] == '/DEST/HEADER/DOC_NUM'


def test_convert_save_alias_still_works(client):
    response = client.post('/convert/save', files={'file': ('proposal.xlsx', proposal_xlsx(), XLSX)}, data=FORM)
    assert response.status_code == 201


@pytest.mark.parametrize('field', ['company', 'version', 'proposal_type'])
def test_convert_and_upload_requires_the_form_fields(client, field):
    response = client.post('/convert-and-upload', files={'file': ('proposal.xlsx', proposal_xlsx(), XLSX)},
                           data={**FORM, field: '  '})
    assert response.status_code == 400


def test_convert_and_upload_returns_502_when_storage_fails(client, monkeypatch):
    def broken(*args, **kwargs):
        raise StorageError('Cannot connect to SFTP')

    monkeypatch.setattr(convert_router, 'save_mapping_package', broken)
    response = client.post('/convert-and-upload', files={'file': ('proposal.xlsx', proposal_xlsx(), XLSX)}, data=FORM)

    assert response.status_code == 502
    assert response.json()['detail'] == 'De bestanden zijn tijdelijk niet bereikbaar'


def test_packages_storage_dependency(monkeypatch):
    monkeypatch.setenv('SFTP_SHARED_HOST', '')
    assert isinstance(convert_router.get_packages_storage(), LocalStorage)
