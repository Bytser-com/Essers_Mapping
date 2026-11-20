"""Central configuration for the Mapping Converter: paths and settings from ``.env``.

``.env`` is read exactly once, here. Same variables as Mapping_Proposal, so both
services point at the same shared SFTP server (sftp-shared).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Mapping_Converter/ folder (this file lives in Mapping_Converter/scripts/).
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / 'data'
LOCAL_SHARED_DIR = DATA_DIR / 'sftp-shared'
PROMPT_PATH = ROOT / 'review_prompt.txt'  # instructions for the Gemini review

_env_loaded = False


# Repo root (Essers_Mapping/): one shared .env for all services.
REPO_ROOT = ROOT.parent


def _load_env() -> None:
    """Read the shared .env in the repo root once. Variables that are already set
    (terminal, Kubernetes secrets) always win: load_dotenv never overrides them."""
    global _env_loaded
    if not _env_loaded:
        load_dotenv(REPO_ROOT / '.env')
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


def packages_remote_dir() -> str:
    """Folder of the mapping packages on the SFTP server (SFTP_SHARED_PACKAGES_DIR, default /Packages)."""
    _load_env()
    return _absolute(os.getenv('SFTP_SHARED_PACKAGES_DIR', ''), '/Packages')


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


# ---------------------------------------------------------------------------
# Gemini review (story 51)
# ---------------------------------------------------------------------------
DEFAULT_REVIEW_TIMEOUT_MS = 60_000


@dataclass(frozen=True)
class ReviewSettings:
    api_key: str
    model: str
    timeout_ms: int = DEFAULT_REVIEW_TIMEOUT_MS


def load_review_settings() -> ReviewSettings:
    """Gemini settings. GEMINI_REVIEW_MODEL overrides the shared GEMINI_MODEL; the timeout
    comes from GEMINI_REVIEW_TIMEOUT_SECONDS, else GEMINI_REVIEW_TIMEOUT_MS (default 60 s)."""
    load_dotenv(REPO_ROOT / '.env', override=False)
    return ReviewSettings(
        api_key=os.getenv('GEMINI_API_KEY', '').strip(),
        model=(os.getenv('GEMINI_REVIEW_MODEL') or os.getenv('GEMINI_MODEL') or '').strip(),
        timeout_ms=_review_timeout_ms(),
    )


def _review_timeout_ms() -> int:
    seconds = os.getenv('GEMINI_REVIEW_TIMEOUT_SECONDS', '').strip()
    if seconds.isdigit():
        return int(seconds) * 1000
    milliseconds = os.getenv('GEMINI_REVIEW_TIMEOUT_MS', '').strip()
    if milliseconds.isdigit():
        return int(milliseconds)
    return DEFAULT_REVIEW_TIMEOUT_MS
