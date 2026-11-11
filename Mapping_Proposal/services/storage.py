"""Shared storage for the proposals: the SFTP server of the infrastructure (sftp-shared).

Two implementations with the same small interface, so services/proposals.py does not
care where the files live:

    SftpStorage    a direct SFTP connection to the shared SFTPGo server. Used when
                   SFTP_SHARED_HOST is set (in Kubernetes: sftp-shared, port 22, see
                   Kubernetes/base/kustomization.yaml and common/secrets.yaml).
    LocalStorage   a normal folder. Used locally when no SFTP server is configured
                   (data/sftp-shared/proposals/) and in the tests (a temporary folder).

Paths are always POSIX paths relative to the storage root, e.g. "ostavel/v1/proposal.json".
Every operation happens inside ``with storage.session() as s:`` so one SFTP connection
is reused for a group of operations and always closed afterwards.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import logging
import os
from pathlib import Path, PurePosixPath
import posixpath
import stat
from typing import Iterator, Protocol

from scripts.errors import StorageError

logger = logging.getLogger(__name__)


class StorageSession(Protocol):
    """Operations on the storage. ``path`` is relative to the root ("" is the root)."""

    def list_dirs(self, path: str) -> list[str]: ...          # names of subfolders; [] if missing
    def exists(self, path: str) -> bool: ...
    def make_dirs(self, path: str) -> None: ...               # like mkdir -p
    def make_dir(self, path: str) -> bool: ...                # False if it already exists
    def read_text(self, path: str) -> str: ...
    def write_text(self, path: str, text: str) -> None: ...   # atomic: never half-written
    def upload_file(self, local_path: Path, path: str) -> None: ...


class Storage(Protocol):
    def session(self):  # context manager that yields a StorageSession
        ...

    def describe(self) -> str: ...


def proposal_storage() -> 'LocalStorage | SftpStorage':
    """Where the proposals are stored: the SFTP server if SFTP_SHARED_HOST is set, else
    the local folder data/sftp-shared/proposals/."""
    from scripts.config import proposals_dir, sftp_shared_config  # read .env at call time

    config = sftp_shared_config()
    if config:
        return SftpStorage(SftpSettings(**config))
    return LocalStorage(proposals_dir())


def _clean(path: str) -> str:
    """Relative POSIX path without '..', so nothing can leave the storage root."""
    parts = [part for part in PurePosixPath(path.replace('\\', '/')).parts if part not in ('', '.', '/')]
    if '..' in parts:
        raise StorageError(f'Invalid path on the shared storage: {path!r}')
    return '/'.join(parts)


# ---------------------------------------------------------------------------
# Local folder (development without SFTP server, and tests)
# ---------------------------------------------------------------------------
class LocalStorage:
    def __init__(self, root: Path):
        self.root = Path(root)

    def describe(self) -> str:
        return f'local folder {self.root}'

    @contextmanager
    def session(self) -> Iterator['LocalStorage']:
        yield self

    def _path(self, path: str) -> Path:
        clean = _clean(path)
        return self.root / clean if clean else self.root

    def list_dirs(self, path: str) -> list[str]:
        folder = self._path(path)
        if not folder.is_dir():
            return []
        return sorted(p.name for p in folder.iterdir() if p.is_dir())

    def exists(self, path: str) -> bool:
        return self._path(path).exists()

    def make_dirs(self, path: str) -> None:
        self._path(path).mkdir(parents=True, exist_ok=True)

    def make_dir(self, path: str) -> bool:
        try:
            self._path(path).mkdir()
            return True
        except FileExistsError:
            return False

    def read_text(self, path: str) -> str:
        return self._path(path).read_text(encoding='utf-8-sig')  # -sig: tolerate a Windows BOM

    def write_text(self, path: str, text: str) -> None:
        target = self._path(path)
        temp = target.with_name(f'.{target.name}.tmp')
        temp.write_text(text, encoding='utf-8')
        os.replace(temp, target)

    def upload_file(self, local_path: Path, path: str) -> None:
        target = self._path(path)
        temp = target.with_name(f'.{target.name}.tmp')
        temp.write_bytes(Path(local_path).read_bytes())
        os.replace(temp, target)


# ---------------------------------------------------------------------------
# SFTP server (sftp-shared in Kubernetes)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SftpSettings:
    host: str
    port: int = 22
    user: str = ''
    password: str = ''
    base_dir: str = '/'          # folder on the server where we may write
    proposals_dir: str = 'Proposals'  # <base_dir>/Proposals, same folder as Version_Control reads
    timeout: float = 15.0


class SftpStorage:
    def __init__(self, settings: SftpSettings):
        self.settings = settings
        if settings.proposals_dir:
            self.root = posixpath.join(settings.base_dir or '/', settings.proposals_dir)
        else:
            self.root = settings.base_dir or '/'

    def describe(self) -> str:
        s = self.settings
        return f'sftp://{s.user}@{s.host}:{s.port}{self.root}'

    @contextmanager
    def session(self) -> Iterator['_SftpSession']:
        try:
            import paramiko
        except ImportError as error:  # pragma: no cover - only without requirements installed
            raise StorageError('paramiko is not installed: pip install -r requirements.txt') from error

        s = self.settings
        try:
            transport = paramiko.Transport((s.host, s.port))
            transport.banner_timeout = s.timeout
            transport.connect(username=s.user, password=s.password)
            client = paramiko.SFTPClient.from_transport(transport)
            client.get_channel().settimeout(s.timeout)
        except Exception as error:
            try:
                transport.close()
            except Exception:
                pass
            raise StorageError(f'Cannot connect to SFTP {s.host}:{s.port} as {s.user!r}: {error}') from error
        try:
            yield _SftpSession(client, self.root)
        finally:
            client.close()
            transport.close()


class _SftpSession:
    def __init__(self, client, root: str):
        self.client = client
        self.root = root

    def _path(self, path: str) -> str:
        clean = _clean(path)
        return posixpath.join(self.root, clean) if clean else self.root

    def _stat(self, remote: str):
        try:
            return self.client.stat(remote)
        except IOError:
            return None

    def list_dirs(self, path: str) -> list[str]:
        try:
            entries = self.client.listdir_attr(self._path(path))
        except IOError:
            return []
        return sorted(e.filename for e in entries if stat.S_ISDIR(e.st_mode or 0))

    def exists(self, path: str) -> bool:
        return self._stat(self._path(path)) is not None

    def make_dirs(self, path: str) -> None:
        remote = self._path(path)
        current = '/' if remote.startswith('/') else ''
        for part in (p for p in remote.split('/') if p):
            current = posixpath.join(current, part) if current else part
            if self._stat(current) is not None:
                continue
            try:
                self.client.mkdir(current)
            except IOError:
                if self._stat(current) is None:  # not created by someone else at the same time
                    raise

    def make_dir(self, path: str) -> bool:
        remote = self._path(path)
        try:
            self.client.mkdir(remote)
            return True
        except IOError:
            if self._stat(remote) is not None:
                return False
            raise

    def read_text(self, path: str) -> str:
        with self.client.open(self._path(path), 'rb') as handle:
            return handle.read().decode('utf-8-sig')

    def write_text(self, path: str, text: str) -> None:
        self._write_atomic(self._path(path), lambda temp: self._put_bytes(temp, text.encode('utf-8')))

    def upload_file(self, local_path: Path, path: str) -> None:
        self._write_atomic(self._path(path), lambda temp: self.client.put(str(local_path), temp))

    def _put_bytes(self, remote: str, data: bytes) -> None:
        with self.client.open(remote, 'wb') as handle:
            handle.write(data)

    def _write_atomic(self, remote: str, write) -> None:
        """Write to a temporary name, then rename, so readers never see a half-written file."""
        temp = posixpath.join(posixpath.dirname(remote), f'.{posixpath.basename(remote)}.tmp')
        write(temp)
        try:
            self.client.posix_rename(temp, remote)  # overwrites (OpenSSH/SFTPGo extension)
        except IOError:
            # Server without posix-rename: remove the old file first, then a normal rename.
            if self._stat(remote) is not None:
                self.client.remove(remote)
            self.client.rename(temp, remote)
