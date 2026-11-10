"""Unit tests for services/storage.py: the local folder and the SFTP connection.

The SFTP tests use a fake paramiko SFTP client that works on a temporary folder, so no
SFTP server is needed. The same ProposalStore code runs on both storages.
"""
from __future__ import annotations

from contextlib import contextmanager
import errno
import os
from pathlib import Path
import sys
import types

import pytest

from scripts.errors import StorageError
from services.proposals import AiStatus, ProposalStatus, ProposalStore
from services.storage import LocalStorage, SftpSettings, SftpStorage, _SftpSession, proposal_storage


# ---------------------------------------------------------------------------
# Fake paramiko SFTP client (only the methods services/storage.py uses)
# ---------------------------------------------------------------------------
class FakeSftpClient:
    """Behaves like paramiko.SFTPClient on top of a local folder (the "server disk")."""

    def __init__(self, disk: Path, posix_rename: bool = True):
        self.disk = disk
        self.supports_posix_rename = posix_rename

    def _local(self, remote: str) -> Path:
        return self.disk / remote.lstrip('/')

    def stat(self, remote):
        path = self._local(remote)
        if not path.exists():
            raise IOError(errno.ENOENT, 'No such file')
        return os.stat(path)

    def listdir_attr(self, remote):
        path = self._local(remote)
        if not path.is_dir():
            raise IOError(errno.ENOENT, 'No such folder')
        return [types.SimpleNamespace(filename=child.name, st_mode=os.stat(child).st_mode)
                for child in path.iterdir()]

    def mkdir(self, remote):
        path = self._local(remote)
        if path.exists() or not path.parent.is_dir():
            raise IOError('Failure')  # SFTP servers give a generic failure
        path.mkdir()

    def open(self, remote, mode):
        return open(self._local(remote), mode)

    def put(self, local, remote):
        self._local(remote).write_bytes(Path(local).read_bytes())

    def posix_rename(self, old, new):
        if not self.supports_posix_rename:
            raise IOError('posix-rename not supported')
        os.replace(self._local(old), self._local(new))

    def rename(self, old, new):
        if self._local(new).exists():
            raise IOError('Failure: target exists')
        os.rename(self._local(old), self._local(new))

    def remove(self, remote):
        self._local(remote).unlink()


class FakeSftpStorage(SftpStorage):
    """SftpStorage whose session uses the fake client instead of a network connection."""

    def __init__(self, disk: Path, base_dir: str = '/upload', posix_rename: bool = True):
        super().__init__(SftpSettings(host='sftp-shared', user='shareduser', base_dir=base_dir))
        self.client = FakeSftpClient(disk, posix_rename)

    @contextmanager
    def session(self):
        yield _SftpSession(self.client, self.root)


@pytest.fixture
def disk(tmp_path):
    root = tmp_path / 'server'
    (root / 'upload').mkdir(parents=True)  # SFTP_SHARED_REMOTE_DIR exists on the server
    return root


# ---------------------------------------------------------------------------
# Choosing the storage from the configuration
# ---------------------------------------------------------------------------
def test_without_sftp_host_the_local_folder_is_used(monkeypatch):
    monkeypatch.setenv('SFTP_SHARED_HOST', '')
    assert isinstance(proposal_storage(), LocalStorage)


def test_with_sftp_host_the_sftp_server_is_used(monkeypatch):
    monkeypatch.setenv('SFTP_SHARED_HOST', 'sftp-shared')
    monkeypatch.setenv('SFTP_SHARED_PORT', '22')
    monkeypatch.setenv('SFTP_SHARED_USER', 'shareduser')
    monkeypatch.setenv('SFTP_SHARED_PASSWORD', 'secret')
    monkeypatch.setenv('SFTP_SHARED_REMOTE_DIR', '/upload')

    storage = proposal_storage()

    assert isinstance(storage, SftpStorage)
    assert storage.settings == SftpSettings(host='sftp-shared', port=22, user='shareduser',
                                            password='secret', base_dir='/upload')
    assert storage.root == '/upload/proposals'
    assert storage.describe() == 'sftp://shareduser@sftp-shared:22/upload/proposals'


def test_invalid_port_falls_back_to_22(monkeypatch):
    monkeypatch.setenv('SFTP_SHARED_HOST', 'sftp-shared')
    monkeypatch.setenv('SFTP_SHARED_PORT', 'abc')
    assert proposal_storage().settings.port == 22


# ---------------------------------------------------------------------------
# Connecting
# ---------------------------------------------------------------------------
def test_unreachable_sftp_server_gives_a_storage_error(monkeypatch):
    class FailingTransport:
        def __init__(self, address):
            self.address = address

        def connect(self, username, password):
            raise OSError('Connection refused')

        def close(self):
            pass

    monkeypatch.setitem(sys.modules, 'paramiko', types.SimpleNamespace(Transport=FailingTransport))
    storage = SftpStorage(SftpSettings(host='sftp-shared', user='shareduser', password='x'))

    with pytest.raises(StorageError, match='sftp-shared:22'):
        with storage.session():
            pass


def test_sftp_connection_is_closed_after_the_session(monkeypatch):
    events = []

    class Transport:
        def __init__(self, address):
            events.append(('connect-to', address))

        def connect(self, username, password):
            events.append(('login', username, password))

        def close(self):
            events.append('transport-closed')

    class Client:
        def get_channel(self):
            return types.SimpleNamespace(settimeout=lambda seconds: None)

        def close(self):
            events.append('client-closed')

    fake_paramiko = types.SimpleNamespace(
        Transport=Transport, SFTPClient=types.SimpleNamespace(from_transport=lambda transport: Client()))
    monkeypatch.setitem(sys.modules, 'paramiko', fake_paramiko)
    storage = SftpStorage(SftpSettings(host='sftp-shared', port=22, user='shareduser', password='pw'))

    with storage.session() as session:
        assert session.root == '/proposals'

    assert events == [('connect-to', ('sftp-shared', 22)), ('login', 'shareduser', 'pw'),
                      'client-closed', 'transport-closed']


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('bad_path', ['../geheim', 'ostavel/../../x', '..'])
def test_paths_cannot_leave_the_storage_root(tmp_path, bad_path):
    with pytest.raises(StorageError):
        LocalStorage(tmp_path).exists(bad_path)


# ---------------------------------------------------------------------------
# ProposalStore on the SFTP server
# ---------------------------------------------------------------------------
def test_new_proposal_is_written_in_the_customer_folder_on_sftp(disk):
    store = ProposalStore(FakeSftpStorage(disk))

    ref = store.create_proposal('Ostavel')

    assert ref.folder == 'ostavel/v1'
    assert (disk / 'upload' / 'proposals' / 'ostavel' / 'v1' / 'proposal.json').is_file()
    [row] = store.list_proposals()
    assert (row.customer, row.version, row.status, row.ai_status) == (
        'Ostavel', 1, ProposalStatus.AI_GENERATING, AiStatus.RUNNING)


def test_next_upload_of_the_same_customer_gets_the_next_version(disk):
    store = ProposalStore(FakeSftpStorage(disk))
    store.create_proposal('Ostavel')

    ref = store.create_proposal('Ostavel')

    assert ref.version == 2
    assert [row.version for row in store.list_proposals(all_versions=True)] == [2, 1]


def test_excel_and_status_are_stored_on_sftp(disk, tmp_path):
    store = ProposalStore(FakeSftpStorage(disk))
    ref = store.create_proposal('Ostavel')
    excel = tmp_path / 'result.xlsx'
    excel.write_bytes(b'excel-bytes')

    store.save_file(ref, excel, 'MProposal-Ostavel_V1.xlsx')
    store.set_status(ref, ProposalStatus.READY_FOR_REVIEW, None)

    folder = disk / 'upload' / 'proposals' / 'ostavel' / 'v1'
    assert (folder / 'MProposal-Ostavel_V1.xlsx').read_bytes() == b'excel-bytes'
    # No temporary files are left behind
    assert sorted(p.name for p in folder.iterdir()) == ['MProposal-Ostavel_V1.xlsx', 'proposal.json']
    [row] = store.list_proposals()
    assert row.status is ProposalStatus.READY_FOR_REVIEW
    assert store.exists(ref)


def test_overwriting_works_on_a_server_without_posix_rename(disk):
    store = ProposalStore(FakeSftpStorage(disk, posix_rename=False))
    ref = store.create_proposal('Ostavel')

    store.set_status(ref, ProposalStatus.AI_GENERATING, AiStatus.FAILED, error='boom')

    [row] = store.list_proposals()
    assert row.ai_status is AiStatus.FAILED


def test_empty_sftp_server_gives_an_empty_overview(disk):
    assert ProposalStore(FakeSftpStorage(disk)).list_proposals() == []


def test_missing_folders_are_created_on_the_server(tmp_path):
    disk = tmp_path / 'server'
    disk.mkdir()
    store = ProposalStore(FakeSftpStorage(disk, base_dir='/upload'))  # /upload does not exist yet

    store.create_proposal('Ostavel')

    assert (disk / 'upload' / 'proposals' / 'ostavel' / 'v1').is_dir()


def test_files_and_broken_versions_next_to_the_versions_are_ignored(disk):
    store = ProposalStore(FakeSftpStorage(disk))
    store.create_proposal('Ostavel')
    customer = disk / 'upload' / 'proposals' / 'ostavel'
    (customer / 'notes.txt').write_text('x')
    (customer / 'v2').mkdir()  # broken: no proposal.json

    assert [row.version for row in store.list_proposals(all_versions=True)] == [1]
