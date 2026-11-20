"""Unit tests for SFTP storage service in Mapping Converter."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from models import MappingEntry, MappingPackage
from sftp_service import (
    SftpConfig,
    SftpFileNotFoundError,
    _sftp_makedirs,
    build_package_sftp_path,
    download_proposal_excel_from_sftp,
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

    with (
        patch("paramiko.Transport", return_value=mock_transport),
        patch("paramiko.SFTPClient.from_transport", return_value=mock_sftp),
        patch("sftp_service._sftp_makedirs"),
    ):
        path = "/Packages/nouryon/v4/outbound/MPackage.json"
        result = save_json_to_sftp('{"mappings": []}', path, config=config)

        assert result == path
        mock_transport.connect.assert_called_once_with(username="testuser", password="secretpassword")
        mock_file.write.assert_called_once_with(b'{"mappings": []}')


def test_save_mapping_package_to_sftp_attaches_metadata():
    package = MappingPackage(mappings=[MappingEntry(source_path="/A/B", target_path="/C/D")])

    with patch(
        "sftp_service.save_json_to_sftp", return_value="/Packages/nouryon/v1/inbound/MPackage.json"
    ) as mock_save:
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


def test_download_proposal_excel_from_sftp_local_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_SFTP_SHARED_DIR", str(tmp_path))
    config = SftpConfig(host="local", proposals_dir="/Proposals")

    # Create dummy proposal directory structure in tmp_path
    proposal_dir = tmp_path / "Proposals" / "nouryon" / "v2" / "inbound"
    proposal_dir.mkdir(parents=True, exist_ok=True)
    excel_file = proposal_dir / "MProposal-Nouryon_V2.xlsx"
    excel_file.write_bytes(b"dummy excel bytes")

    contents, path = download_proposal_excel_from_sftp(
        company="Nouryon",
        version="2",
        proposal_type="inbound",
        config=config,
    )
    assert contents == b"dummy excel bytes"
    assert "MProposal-Nouryon_V2.xlsx" in path


def test_download_proposal_excel_from_sftp_with_mocked_paramiko():
    config = SftpConfig(
        host="mock-sftp-host",
        port=2222,
        user="testuser",
        password="secretpassword",
        proposals_dir="/Proposals",
    )

    mock_transport = MagicMock()
    mock_sftp = MagicMock()
    mock_file = MagicMock()
    mock_file.read.return_value = b"remote excel bytes"
    mock_sftp.open.return_value.__enter__.return_value = mock_file

    def fake_listdir(path):
        if path in ("/Proposals", "/proposals"):
            return ["nouryon"]
        if path == "/Proposals/nouryon":
            return ["v2"]
        if path == "/Proposals/nouryon/v2":
            return ["inbound"]
        if path == "/Proposals/nouryon/v2/inbound":
            return ["MProposal-Nouryon_V2.xlsx", "proposal.json"]
        raise OSError("Directory not found")

    mock_sftp.listdir.side_effect = fake_listdir

    with (
        patch("paramiko.Transport", return_value=mock_transport),
        patch("paramiko.SFTPClient.from_transport", return_value=mock_sftp),
    ):
        contents, path = download_proposal_excel_from_sftp(
            company="nouryon",
            version="v2",
            proposal_type="inbound",
            config=config,
        )
        assert contents == b"remote excel bytes"
        assert path == "/Proposals/nouryon/v2/inbound/MProposal-Nouryon_V2.xlsx"


def test_download_proposal_excel_from_sftp_not_found():
    config = SftpConfig(
        host="mock-sftp-host",
        port=2222,
        user="testuser",
        password="secretpassword",
        proposals_dir="/Proposals",
    )

    mock_transport = MagicMock()
    mock_sftp = MagicMock()
    mock_sftp.listdir.return_value = []  # empty proposals dir

    with (
        patch("paramiko.Transport", return_value=mock_transport),
        patch("paramiko.SFTPClient.from_transport", return_value=mock_sftp),
    ):
        try:
            download_proposal_excel_from_sftp(
                company="nonexistent",
                version="v1",
                proposal_type="inbound",
                config=config,
            )
            assert False, "Expected SftpFileNotFoundError"
        except SftpFileNotFoundError as exc:
            assert "not found" in str(exc).lower()
