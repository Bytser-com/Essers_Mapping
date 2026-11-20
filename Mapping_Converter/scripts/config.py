"""Central configuration for the Mapping Converter: paths and settings from ``.env``.

``.env`` is read exactly once, here. Same variables as Mapping_Proposal, so both
services point at the same shared SFTP server (sftp-shared).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Mapping_Converter/ folder (this file lives in Mapping_Converter/scripts/).
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / 'data'
LOCAL_SHARED_DIR = DATA_DIR / 'sftp-shared'

_env_loaded = False


def _load_env() -> None:
    global _env_loaded
    if not _env_loaded:
        load_dotenv(ROOT / '.env')
        _env_loaded = True


def _sftp_port() -> int:
    try:
        return int(os.getenv('SFTP_SHARED_PORT', '22'))
    except ValueError:
        return 22


def _absolute(folder: str, default: str) -> str:
    folder = folder.strip() or default
    return folder if folder.startswith('/') else '/' + folder


def sftp_shared_config() -> dict | None:
    """Connection settings for the proposals on sftp-shared, or None when SFTP_SHARED_HOST is empty."""
    _load_env()
    host = os.getenv('SFTP_SHARED_HOST', '').strip()
    if not host:
        return None
    return {
        'host': host,
        'port': _sftp_port(),
        'user': os.getenv('SFTP_SHARED_USER', '').strip(),
        'password': os.getenv('SFTP_SHARED_PASSWORD', ''),
        'base_dir': _absolute(os.getenv('SFTP_SHARED_PROPOSALS_DIR', ''), '/Proposals'),
        'proposals_dir': '',
    }


def sftp_shared_packages_config() -> dict | None:
    """Connection settings for the packages on sftp-shared, or None when SFTP_SHARED_HOST is empty."""
    _load_env()
    host = os.getenv('SFTP_SHARED_HOST', '').strip()
    if not host:
        return None
    return {
        'host': host,
        'port': _sftp_port(),
        'user': os.getenv('SFTP_SHARED_USER', '').strip(),
        'password': os.getenv('SFTP_SHARED_PASSWORD', ''),
        'base_dir': _absolute(os.getenv('SFTP_SHARED_PACKAGES_DIR', ''), '/Packages'),
        'proposals_dir': '',
    }


def shared_storage_dir() -> Path:
    """Local stand-in for the SFTP server (used when SFTP_SHARED_HOST is not set)."""
    return LOCAL_SHARED_DIR


def proposals_dir() -> Path:
    return shared_storage_dir() / 'proposals'


def packages_dir() -> Path:
    return shared_storage_dir() / 'packages'


def cors_origins() -> list[str]:
    """Browser origins allowed to call the API directly (comma-separated CORS_ORIGINS)."""
    _load_env()
    return [origin.strip() for origin in os.getenv('CORS_ORIGINS', '').split(',') if origin.strip()]