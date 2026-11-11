"""Proposals on a real SFTP server: the local Docker server from docker-compose.sftp.yml.

Start it first:  docker compose -f docker-compose.sftp.yml up -d
Run:             pytest -m integration
The tests are skipped when the server is not running, so a normal ``pytest`` never fails on it.
"""
from __future__ import annotations

import socket
import uuid

import pytest

from services.proposals import ProposalStatus, ProposalStore, customer_folder_name
from services.storage import SftpSettings, SftpStorage

pytestmark = pytest.mark.integration

SETTINGS = SftpSettings(host='localhost', port=2222, user='shareduser', password='devpassword',
                        base_dir='/')  # -> /Proposals, as in docker-compose.sftp.yml


def _server_running() -> bool:
    try:
        with socket.create_connection((SETTINGS.host, SETTINGS.port), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture
def store():
    pytest.importorskip('paramiko')
    if not _server_running():
        pytest.skip('Docker SFTP server not running (docker compose -f docker-compose.sftp.yml up -d)')
    storage = SftpStorage(SETTINGS)
    yield ProposalStore(storage)


@pytest.fixture
def customer(store):
    """A unique customer per test; its folder is removed from the server afterwards."""
    name = f'Pytest {uuid.uuid4().hex[:8]}'
    yield name
    with store.storage.session() as s:
        _remove_tree(s.client, f'{s.root}/{customer_folder_name(name)}')


def _remove_tree(client, path):
    import stat
    try:
        entries = client.listdir_attr(path)
    except IOError:
        return
    for entry in entries:
        child = f'{path}/{entry.filename}'
        if stat.S_ISDIR(entry.st_mode):
            _remove_tree(client, child)
        else:
            client.remove(child)
    client.rmdir(path)


def test_proposal_and_excel_are_stored_on_the_sftp_server(store, customer, tmp_path):
    excel = tmp_path / 'result.xlsx'
    excel.write_bytes(b'excel-bytes')

    ref = store.create_proposal(customer)
    store.save_file(ref, excel, 'MProposal-Test_V1.xlsx')
    store.set_status(ref, ProposalStatus.READY_FOR_REVIEW, None)

    rows = [row for row in store.list_proposals() if row.customer == customer]
    assert [(row.version, row.status) for row in rows] == [(1, ProposalStatus.READY_FOR_REVIEW)]
    with store.storage.session() as s:
        assert s.exists(f'{ref.folder}/MProposal-Test_V1.xlsx')


def test_second_upload_of_the_same_customer_gets_version_2(store, customer):
    store.create_proposal(customer)
    assert store.create_proposal(customer).version == 2
