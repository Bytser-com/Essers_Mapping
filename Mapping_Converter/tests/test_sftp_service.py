"""Unit tests for SFTP storage service in Mapping Converter."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from models import MappingEntry, MappingPackage
from sftp_service import (
    SftpConfig,
    _sftp_makedirs,
    build_package_sftp_path,
    format_semver,
    normalize_slug,
    normalize_version,
    save_json_to_sftp,
    save_mapping_package_to_sftp,
)


def test_normalize_version():
    assert normalize_version(3) == "v3"
    assert normalize_version("3") == "v3"
    assert normalize_version("v3") == "v3"
    assert normalize_version("V4") == "v4"
    assert normalize_version("version12") == "v12"
    assert normalize_version("") == "v1"


def test_format_semver():
    assert format_semver("1.0.0") == "1.0.0"
    assert format_semver("v3") == "3.0.0"
    assert format_semver("4") == "4.0.0"
    assert format_semver("V12") == "12.0.0"


def test_normalize_slug():
    assert normalize_slug("Nouryon") == "nouryon"
    assert normalize_slug("  Inbound  ") == "inbound"
    assert normalize_slug("Order Message 01") == "order_message_01"


def test_build_package_sftp_path():
    path1 = build_package_sftp_path(
        company="nouryon",
        version="v3",
        message_type="inbound",
        base_dir="/Packages",
    )
    assert path1 == "/Packages/nouryon/v3/inbound/MPackage.json"

    path2 = build_package_sftp_path(
        company="nouryon",
        version="v4",
        message_type="outbound",
        base_dir="/Packages",
    )
    assert path2 == "/Packages/nouryon/v4/outbound/MPackage.json"

    path3 = build_package_sftp_path(
        company="Kelmont",
        version=2,
        message_type="Inbound",
        base_dir="/Packages",
    )
    assert path3 == "/Packages/kelmont/v2/inbound/MPackage.json"


def test_sftp_makedirs_creates_hierarchy():
    mock_sftp = MagicMock()
    mock_sftp.stat.side_effect = [OSError("Not found"), OSError("Not found"), None]

    _sftp_makedirs(mock_sftp, "/Packages/company/v1")
    assert mock_sftp.mkdir.call_count >= 1


def test_save_json_to_sftp_local_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("SFTP_SHARED_HOST", "local")
    config = SftpConfig(host="local", packages_dir="/Packages")

    content = json.dumps({"test": 123})
    target_path = "/Packages/mock_corp/v1/inbound/MPackage.json"

    with patch("sftp_service.Path") as mock_path_cls:
        fake_parents = [None, tmp_path]
        mock_file_path = MagicMock()
        mock_file_path.resolve.return_value.parents = fake_parents
        mock_path_cls.return_value = mock_file_path
        mock_path_cls.side_effect = lambda *args: Path(*args)

        saved_path = save_json_to_sftp(content, target_path, config=config)
        assert saved_path == target_path


def test_save_json_to_sftp_with_mocked_paramiko():
    config = SftpConfig(
        host="mock-sftp-host",
        port=2222,
        user="testuser",
        password="secretpassword",
        packages_dir="/Packages",
    )

    mock_transport = MagicMock()
    mock_sftp = MagicMock()
    mock_file = MagicMock()
    mock_sftp.open.return_value.__enter__.return_value = mock_file

    with patch("paramiko.Transport", return_value=mock_transport), \
         patch("paramiko.SFTPClient.from_transport", return_value=mock_sftp), \
         patch("sftp_service._sftp_makedirs"):

        path = "/Packages/nouryon/v4/outbound/MPackage.json"
        result = save_json_to_sftp('{"mappings": []}', path, config=config)

        assert result == path
        mock_transport.connect.assert_called_once_with(username="testuser", password="secretpassword")
        mock_file.write.assert_called_once_with(b'{"mappings": []}')


def test_save_mapping_package_to_sftp_attaches_metadata():
    package = MappingPackage(
        mappings=[
            MappingEntry(source_path="/A/B", target_path="/C/D")
        ]
    )

    with patch("sftp_service.save_json_to_sftp", return_value="/Packages/nouryon/v1/inbound/MPackage.json") as mock_save:
        res = save_mapping_package_to_sftp(
            package=package,
            company="Nouryon",
            version="1",
            message_type="inbound",
            user_created="analist_a",
            package_version="1.0.0",
        )
        assert res == "/Packages/nouryon/v1/inbound/MPackage.json"
        assert mock_save.called
        assert package.schema_version == "1.0"
        assert package.meta is not None
        assert package.meta.client_name == "nouryon"
        assert package.meta.package_version == "1.0.0"
        assert package.meta.package_type == "inbound"
        assert package.meta.user_created == "analist_a"
        assert "T" in package.meta.date_created
