"""Storing JSON mapping packages on the shared storage (story 54).

Layout on the storage (packages root = SFTP_SHARED_PACKAGES_DIR, default /Packages):

    <company>/v<N>/<proposal_type>/MPackage.json      e.g. nouryon/v4/outbound/MPackage.json

Names are normalized (lowercase, safe characters) so every service finds the same file.
The file is written atomically through services/storage.py, so a reader never sees a
half-written package.
"""
from __future__ import annotations

import posixpath
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from scripts.config import packages_remote_dir, sftp_shared_packages_config
from scripts.models import MappingPackage, PackageMeta
from services.excel_converter import parse_mapping_excel
from services.storage import Storage

PACKAGE_FILENAME = 'MPackage.json'
DEFAULT_USER = 'analist_a'


def normalize_version(version: str | int) -> str:
    """Normalize a folder version to 'v<N>' (3 -> 'v3', 'V4' -> 'v4'); empty gives 'v1'."""
    text = str(version).strip().lower()
    match = re.search(r'\d+', text)
    if match:
        return f'v{match.group(0)}'
    return text or 'v1'


def format_semver(version: str | int) -> str:
    """Format a version as semantic version ('v4' or '4' -> '4.0.0', '1.0.0' stays '1.0.0')."""
    text = str(version).strip()
    if '.' in text:
        return text.lstrip('vV')
    match = re.search(r'\d+', text)
    if match:
        return f'{match.group(0)}.0.0'
    return '1.0.0'


def normalize_slug(text: str) -> str:
    """Normalize a company name or proposal type to a clean lowercase folder name."""
    cleaned = text.strip().lower()
    return re.sub(r'[^\w.-]+', '_', cleaned).strip('_')


def build_package_path(company: str, version: str | int, proposal_type: str) -> str:
    """Path of the package relative to the packages root, e.g. 'nouryon/v3/inbound/MPackage.json'."""
    return posixpath.join(normalize_slug(company), normalize_version(version), normalize_slug(proposal_type),
                          PACKAGE_FILENAME)


def remote_package_path(relative_path: str) -> str:
    """Full path on the SFTP server, e.g. '/Packages/nouryon/v3/inbound/MPackage.json'."""
    return posixpath.join(packages_remote_dir(), relative_path)


def describe_packages_server() -> str:
    """'host:port' of the packages SFTP server, or 'local-filesystem' without SFTP."""
    config = sftp_shared_packages_config()
    return f"{config['host']}:{config['port']}" if config else 'local-filesystem'


def save_mapping_package(
    storage: Storage,
    package: MappingPackage,
    company: str,
    version: str | int,
    proposal_type: str,
    *,
    user_created: str = DEFAULT_USER,
    package_version: str | None = None,
    now: datetime | None = None,
) -> str:
    """Add the metadata header (when missing) and store the package; returns the full remote path."""
    if package.meta is None:
        package.meta = PackageMeta(
            client_name=normalize_slug(company),
            package_version=package_version or format_semver(version),
            package_type=normalize_slug(proposal_type),
            date_created=(now or datetime.now(UTC)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            user_created=user_created or DEFAULT_USER,
        )

    relative_path = build_package_path(company, version, proposal_type)
    with storage.session() as s:
        s.make_dirs(posixpath.dirname(relative_path))
        s.write_text(relative_path, package.model_dump_json(indent=2))
    return remote_package_path(relative_path)


def convert_excel_to_package(
    storage: Storage,
    excel_source: str | Path | bytes | BinaryIO,
    company: str,
    version: str | int,
    proposal_type: str,
    *,
    user_created: str = DEFAULT_USER,
    package_version: str | None = None,
) -> tuple[MappingPackage, str]:
    """Parse an Excel proposal and store it as a mapping package; returns (package, remote path)."""
    package = parse_mapping_excel(excel_source)
    path = save_mapping_package(storage, package, company, version, proposal_type,
                                user_created=user_created, package_version=package_version)
    return package, path
