"""Unit tests for storage.py with local fallback and mocked SFTP connection."""
from __future__ import annotations

import io
from pathlib import Path
import stat
from unittest.mock import MagicMock, patch

import pytest

from Mapping_Proposal.scripts.config import SFTPSettings
from Mapping_Proposal.scripts.errors import StorageError
from Mapping_Proposal.scripts.storage import (
    ensure_customer_directory,
    list_customers,
    sanitize_customer_name,
    save_customer_file,
)


def test_sanitize_customer_name_valid():
    assert sanitize_customer_name('Ostavel') == 'Ostavel'
    assert sanitize_customer_name('  Klant-ABC 123  ') == 'Klant-ABC 123'
    assert sanitize_customer_name('Acme B.V.') == 'Acme B.V'


def test_sanitize_customer_name_invalid():
    with pytest.raises(StorageError, match='Klantnaam mag niet leeg zijn'):
        sanitize_customer_name('   ')

    with pytest.raises(StorageError, match='directory traversal'):
        sanitize_customer_name('../secret')

    with pytest.raises(StorageError, match='directory traversal'):
        sanitize_customer_name('..')


def test_local_storage_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    storage_dir = tmp_path / 'sftp_storage'
    monkeypatch.setattr('Mapping_Proposal.scripts.storage.SFTP_STORAGE_DIR', storage_dir)

    settings = SFTPSettings(host='', port=22, user='', password='', base_dir='customers')

    # Ensure customer directory
    path = ensure_customer_directory('Klant A', settings=settings)
    assert Path(path).is_dir()
    assert (storage_dir / 'Klant A').exists()

    # Save customer file
    content = b'<test>xml content</test>'
    file_path = save_customer_file('Klant A', 'order.xml', content, settings=settings)
    assert Path(file_path).exists()
    assert Path(file_path).read_bytes() == content

    # Add second customer
    ensure_customer_directory('Klant B', settings=settings)

    # List customers
    customers = list_customers(settings=settings)
    assert customers == ['Klant A', 'Klant B']


def test_remote_sftp_storage(monkeypatch: pytest.MonkeyPatch):
    settings = SFTPSettings(
        host='sftp.essers.local',
        port=2022,
        user='testuser',
        password='secretpassword',
        base_dir='customers',
    )

    mock_sftp = MagicMock()
    mock_transport = MagicMock()

    # Stat returns False for dir existence check initially
    mock_sftp.stat.side_effect = IOError('File not found')

    with patch('Mapping_Proposal.scripts.storage.paramiko') as mock_paramiko:
        mock_paramiko.Transport.return_value = mock_transport
        mock_paramiko.SFTPClient.from_transport.return_value = mock_sftp

        # Test ensure customer directory
        remote_dir = ensure_customer_directory('Ostavel', settings=settings)
        assert remote_dir == 'customers/Ostavel'
        assert mock_sftp.mkdir.called

        # Test save customer file
        remote_file = save_customer_file('Ostavel', 'delivery.xml', b'<xml/>', settings=settings)
        assert remote_file == 'customers/Ostavel/delivery.xml'
        assert mock_sftp.putfo.called

        # Test list customers
        entry_a = MagicMock()
        entry_a.filename = 'Klant1'
        entry_a.st_mode = stat.S_IFDIR

        entry_b = MagicMock()
        entry_b.filename = 'Klant2'
        entry_b.st_mode = stat.S_IFDIR

        mock_sftp.stat.side_effect = None  # Directory exists
        mock_attr = MagicMock()
        mock_attr.st_mode = stat.S_IFDIR
        mock_sftp.stat.return_value = mock_attr
        mock_sftp.listdir_attr.return_value = [entry_a, entry_b]

        customers = list_customers(settings=settings)
        assert customers == ['Klant1', 'Klant2']
