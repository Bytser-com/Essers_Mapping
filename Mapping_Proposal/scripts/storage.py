"""Storage functions for saving customer folders and files to SFTP or local fallback."""
from __future__ import annotations

from contextlib import contextmanager
import io
import os
from pathlib import Path
import posixpath
import re
import stat
from typing import Generator

from .config import SFTP_STORAGE_DIR, SFTPSettings, load_sftp_settings
from .errors import StorageError

try:
    import paramiko
except ImportError:
    paramiko = None  # type: ignore


def sanitize_customer_name(name: str) -> str:
    """Sanitize customer name to prevent directory traversal and invalid path characters.

    Raises:
        StorageError: If the name is empty or contains only invalid characters.
    """
    clean = name.strip()
    if not clean:
        raise StorageError('Klantnaam mag niet leeg zijn.')

    # Disallow directory traversal sequences
    if '..' in clean or clean in ('.', '/'):
        raise StorageError('Ongeldige klantnaam: directory traversal is niet toegestaan.')

    # Replace forbidden path/filesystem characters with underscores
    clean = re.sub(r'[\\/*?:"<>|\x00]', '_', clean)
    clean = clean.strip('. ')

    if not clean:
        raise StorageError('Ongeldige klantnaam.')

    return clean


@contextmanager
def _connect_sftp(settings: SFTPSettings) -> Generator[paramiko.SFTPClient, None, None]:
    """Establish an SFTP session with error handling."""
    if paramiko is None:
        raise StorageError('Paramiko bibliotheek is niet geïnstalleerd voor SFTP-verbindingen.')

    try:
        transport = paramiko.Transport((settings.host, settings.port))
        transport.connect(username=settings.user, password=settings.password)
        sftp = paramiko.SFTPClient.from_transport(transport)
    except Exception as exc:
        raise StorageError(f'SFTP verbinding mislukt naar {settings.host}:{settings.port}: {exc}') from exc

    try:
        yield sftp
    finally:
        try:
            sftp.close()
        except Exception:
            pass
        try:
            transport.close()
        except Exception:
            pass


def _sftp_dir_exists(sftp: paramiko.SFTPClient, path: str) -> bool:
    """Check whether a remote path exists and is a directory."""
    try:
        attr = sftp.stat(path)
        return stat.S_ISDIR(attr.st_mode)
    except IOError:
        return False


def _sftp_ensure_dir(sftp: paramiko.SFTPClient, path: str) -> None:
    """Recursively create remote directory if it does not exist."""
    normalized = posixpath.normpath(path)
    parts = normalized.split('/')
    current = '/' if normalized.startswith('/') else ''

    for part in parts:
        if not part:
            continue
        current = posixpath.join(current, part)
        if not _sftp_dir_exists(sftp, current):
            try:
                sftp.mkdir(current)
            except IOError:
                # Might have been created concurrently or already exists
                if not _sftp_dir_exists(sftp, current):
                    raise


def ensure_customer_directory(customer_name: str, settings: SFTPSettings | None = None) -> str:
    """Create customer directory on SFTP server (or local fallback storage).

    Returns:
        The path of the created/ensured directory.
    """
    clean_name = sanitize_customer_name(customer_name)
    cfg = settings or load_sftp_settings()

    if not cfg.host:
        # Local fallback mode
        target_dir = SFTP_STORAGE_DIR / clean_name
        target_dir.mkdir(parents=True, exist_ok=True)
        return str(target_dir)

    # Remote SFTP mode
    with _connect_sftp(cfg) as sftp:
        remote_base = cfg.base_dir.strip('/')
        remote_customer_dir = posixpath.join(remote_base, clean_name) if remote_base else clean_name
        _sftp_ensure_dir(sftp, remote_customer_dir)
        return remote_customer_dir


def save_customer_file(
    customer_name: str,
    file_name: str,
    content: bytes,
    settings: SFTPSettings | None = None,
) -> str:
    """Save an uploaded file directly into the customer's directory.

    Returns:
        The path of the saved file.
    """
    clean_customer = sanitize_customer_name(customer_name)
    clean_file_name = Path(file_name).name
    if not clean_file_name:
        raise StorageError('Bestandsnaam is ongeldig.')

    cfg = settings or load_sftp_settings()

    if not cfg.host:
        # Local fallback mode
        target_dir = SFTP_STORAGE_DIR / clean_customer
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / clean_file_name
        file_path.write_bytes(content)
        return str(file_path)

    # Remote SFTP mode
    with _connect_sftp(cfg) as sftp:
        remote_base = cfg.base_dir.strip('/')
        remote_customer_dir = posixpath.join(remote_base, clean_customer) if remote_base else clean_customer
        _sftp_ensure_dir(sftp, remote_customer_dir)

        remote_file_path = posixpath.join(remote_customer_dir, clean_file_name)
        sftp.putfo(io.BytesIO(content), remote_file_path)
        return remote_file_path


def list_customers(settings: SFTPSettings | None = None) -> list[str]:
    """Retrieve list of all customer names from SFTP server (or local fallback storage)."""
    cfg = settings or load_sftp_settings()

    if not cfg.host:
        # Local fallback mode
        if not SFTP_STORAGE_DIR.exists():
            return []
        customers = [
            item.name
            for item in SFTP_STORAGE_DIR.iterdir()
            if item.is_dir() and not item.name.startswith('.')
        ]
        return sorted(customers)

    # Remote SFTP mode
    with _connect_sftp(cfg) as sftp:
        remote_base = cfg.base_dir.strip('/') or '.'
        if not _sftp_dir_exists(sftp, remote_base):
            return []

        entries = sftp.listdir_attr(remote_base)
        customers = [
            entry.filename
            for entry in entries
            if stat.S_ISDIR(entry.st_mode) and not entry.filename.startswith('.')
        ]
        return sorted(customers)
