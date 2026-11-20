"""SFTP storage service for Mapping Converter: stores JSON mapping packages on SFTP."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
import posixpath
import re
from typing import Any

from models import MappingPackage, PackageMeta

logger = logging.getLogger(__name__)

# Try loading .env if python-dotenv is present
try:
    from dotenv import load_dotenv

    for candidate in [
        Path(__file__).resolve().parents[1] / ".env",
        Path(__file__).resolve().parents[2] / ".env",
        Path(__file__).resolve().parent / ".env",
    ]:
        if candidate.is_file():
            load_dotenv(candidate)
            break
except ImportError:
    pass


class SftpError(Exception):
    """Raised when an error occurs during SFTP operations."""
    pass


@dataclass(frozen=True)
class SftpConfig:
    host: str
    port: int = 2222
    user: str = "shareduser"
    password: str = "devpassword"
    packages_dir: str = "/Packages"
    allow_unknown_keys: bool = True
    timeout: float = 15.0


def get_sftp_config() -> SftpConfig:
    """Read SFTP configuration from environment variables with smart dev defaults."""
    host = os.getenv("SFTP_SHARED_HOST", "localhost").strip()
    try:
        port = int(os.getenv("SFTP_SHARED_PORT", "2222"))
    except ValueError:
        port = 2222

    pkg_dir = os.getenv("SFTP_SHARED_PACKAGES_DIR", "/Packages").strip() or "/Packages"
    if not pkg_dir.startswith("/"):
        pkg_dir = "/" + pkg_dir

    allow_unknown = os.getenv("SFTP_ALLOW_UNKNOWN_KEYS", "true").strip().lower() in (
        "true",
        "1",
        "yes",
    )

    user = os.getenv("SFTP_SHARED_USER", "shareduser").strip() or "shareduser"
    password = os.getenv("SFTP_SHARED_PASSWORD", "").strip()
    if not password and host in ("localhost", "127.0.0.1"):
        password = "devpassword"

    return SftpConfig(
        host=host,
        port=port,
        user=user,
        password=password,
        packages_dir=pkg_dir,
        allow_unknown_keys=allow_unknown,
    )


def normalize_version(version: str | int) -> str:
    """Normalize folder version to 'v<N>' format (e.g. 3 -> 'v3', 'V4' -> 'v4')."""
    v_str = str(version).strip().lower()
    match = re.search(r"\d+", v_str)
    if match:
        return f"v{match.group(0)}"
    return v_str if v_str else "v1"


def format_semver(version: str | int) -> str:
    """Format version into semantic version (e.g. 'v4' or '4' -> '4.0.0', '1.0.0' -> '1.0.0')."""
    v_str = str(version).strip()
    if "." in v_str:
        return v_str.lstrip("vV")
    match = re.search(r"\d+", v_str)
    if match:
        return f"{match.group(0)}.0.0"
    return "1.0.0"


def normalize_slug(text: str) -> str:
    """Normalize company name or message type to clean lowercase string."""
    cleaned = text.strip().lower()
    return re.sub(r"[^\w.-]+", "_", cleaned).strip("_")


def build_package_sftp_path(
    company: str,
    version: str | int,
    message_type: str,
    base_dir: str | None = None,
) -> str:
    """Build the normalized remote path on the SFTP server.

    Example:
        /Packages/nouryon/v3/inbound/MPackage.json
    """
    clean_company = normalize_slug(company)
    clean_version = normalize_version(version)
    clean_type = normalize_slug(message_type)
    filename = "MPackage.json"

    if base_dir is None:
        cfg = get_sftp_config()
        base_dir = cfg.packages_dir

    base = base_dir.rstrip("/")
    return posixpath.join(base, clean_company, clean_version, clean_type, filename)


def _sftp_makedirs(sftp_client: Any, remote_dir: str) -> None:
    """Recursively create directories over SFTP."""
    parts = [p for p in remote_dir.split("/") if p]
    current = "/" if remote_dir.startswith("/") else ""
    for part in parts:
        current = posixpath.join(current, part)
        try:
            sftp_client.stat(current)
        except OSError:
            try:
                sftp_client.mkdir(current)
            except OSError:
                pass


def save_json_to_sftp(
    json_content: str | bytes,
    remote_path: str,
    config: SftpConfig | None = None,
) -> str:
    """Upload a JSON string or bytes to the SFTP server at the given remote path.

    If host is explicitly set to 'none' or 'local', falls back to local storage under
    `data/sftp-shared` so offline tests can run without an active SFTP container.
    """
    if config is None:
        config = get_sftp_config()

    if isinstance(json_content, str):
        data_bytes = json_content.encode("utf-8")
    else:
        data_bytes = json_content

    if config.host.lower() in ("none", "local", "offline"):
        local_base = (
            Path(__file__).resolve().parents[1] / "data" / "sftp-shared"
        )
        clean_rel = remote_path.lstrip("/")
        local_target = local_base / clean_rel
        local_target.parent.mkdir(parents=True, exist_ok=True)
        local_target.write_bytes(data_bytes)
        logger.info("SFTP host set to '%s'. Saved locally to: %s", config.host, local_target)
        return remote_path

    try:
        import paramiko
    except ImportError as exc:
        raise SftpError(
            "Het pakket 'paramiko' is niet geïnstalleerd. Installeer het via: pip install paramiko"
        ) from exc

    transport = None
    try:
        transport = paramiko.Transport((config.host, config.port))
        transport.banner_timeout = config.timeout
        transport.connect(username=config.user, password=config.password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        sftp.get_channel().settimeout(config.timeout)

        remote_dir = posixpath.dirname(remote_path)
        _sftp_makedirs(sftp, remote_dir)

        with sftp.open(remote_path, "wb") as remote_file:
            remote_file.write(data_bytes)

        logger.info("Mapping package successfully uploaded to SFTP %s:%s: %s", config.host, config.port, remote_path)
        return remote_path
    except Exception as exc:
        msg = f"Fout bij uploaden naar SFTP {config.host}:{config.port} ({remote_path}): {exc}"
        logger.error(msg)
        raise SftpError(msg) from exc
    finally:
        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass


def save_mapping_package_to_sftp(
    package: MappingPackage,
    company: str,
    version: str | int,
    message_type: str,
    user_created: str = "analist_a",
    package_version: str | None = None,
    config: SftpConfig | None = None,
) -> str:
    """Ensure metadata header is present and upload the MappingPackage directly to SFTP."""
    if config is None:
        config = get_sftp_config()

    clean_company = normalize_slug(company)
    clean_type = normalize_slug(message_type)
    resolved_pkg_ver = package_version or format_semver(version)

    # Attach metadata header if not already present
    if package.meta is None:
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        package.meta = PackageMeta(
            client_name=clean_company,
            package_version=resolved_pkg_ver,
            package_type=clean_type,
            date_created=now_utc,
            user_created=user_created or "analist_a",
        )

    remote_path = build_package_sftp_path(
        company=company,
        version=version,
        message_type=message_type,
        base_dir=config.packages_dir,
    )
    json_str = package.model_dump_json(indent=2)
    return save_json_to_sftp(json_str, remote_path, config=config)
