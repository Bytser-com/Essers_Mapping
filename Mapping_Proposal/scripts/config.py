"""Central configuration: project paths and settings from ``.env``.

``.env`` is read exactly once, here. Other modules call ``load_settings()``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# ai_tool/ folder (this file lives in ai_tool/scripts/).
ROOT = Path(__file__).resolve().parent.parent

# Fixed project locations. Change them here instead of in every script.

DATA_DIR = ROOT / 'data'
SOURCE_DIR = DATA_DIR / 'source'
HISTORICAL_DIR = (
    Path(os.getenv('HISTORICAL_DIR')) if os.getenv('HISTORICAL_DIR')
    else (DATA_DIR / 'historical' if (DATA_DIR / 'historical').is_dir() and any((DATA_DIR / 'historical').iterdir())
          else (ROOT / 'tests' / 'fixtures' / 'historical' if (ROOT / 'tests' / 'fixtures' / 'historical').is_dir()
                else DATA_DIR / 'historical'))
)
OUTPUT_DIR = ROOT / 'output'
RUNS_DIR = OUTPUT_DIR / 'runs'
TEMPLATE_PATH = ROOT / 'templates' / 'mapping_template.xlsx'
PROMPT_PATH = ROOT / 'prompt.txt'

DEFAULT_MODEL = 'gemini-3.5-flash-lite'

# Remembers whether .env was already read, so it is loaded only once per process.
_env_loaded = False


def _load_env() -> None:
    global _env_loaded
    if not _env_loaded:
        load_dotenv(ROOT / '.env')
        _env_loaded = True


# frozen=True: the settings cannot be changed by accident after loading.
@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    gemini_timeout_ms: int


def load_settings() -> Settings:
    """Read the current settings from the environment (after loading ``.env``)."""
    _load_env()
    # A non-numeric timeout in .env falls back to the default of 120 seconds.
    try:
        timeout = int(os.getenv('GEMINI_TIMEOUT_MS', '120000'))
    except ValueError:
        timeout = 120000
    return Settings(
        gemini_api_key=os.getenv('GEMINI_API_KEY', '').strip(),
        # An empty GEMINI_MODEL= line also falls back to the default model.
        gemini_model=os.getenv('GEMINI_MODEL', '').strip() or DEFAULT_MODEL,
        gemini_timeout_ms=timeout,
    )


# ---------------------------------------------------------------------------
# Shared storage: the SFTPGo server of the infrastructure (sftp-shared). This service
# connects to it directly over SFTP (services/storage.py). The SFTP_SHARED_* variables
# come from the common-config ConfigMap and the sftp-shared-credentials Secret in
# Kubernetes (Kubernetes/base/kustomization.yaml); locally put them in .env.
# Without SFTP_SHARED_HOST a local stand-in folder is used: data/sftp-shared/
# (data/ is not in Git).
# ---------------------------------------------------------------------------
LOCAL_SHARED_DIR = DATA_DIR / 'sftp-shared'


def sftp_shared_config() -> dict | None:
    """Connection settings for the shared SFTP server, or None when SFTP_SHARED_HOST is empty."""
    _load_env()
    host = os.getenv('SFTP_SHARED_HOST', '').strip()
    if not host:
        return None
    try:
        port = int(os.getenv('SFTP_SHARED_PORT', '22'))
    except ValueError:
        port = 22
    base = os.getenv('SFTP_SHARED_REMOTE_DIR', '').strip() or '/'
    explicit_prop = os.getenv('SFTP_SHARED_PROPOSALS_DIR')
    if explicit_prop is not None and explicit_prop.strip():
        proposals_dir = explicit_prop.strip().strip('/')
    elif base.rstrip('/').endswith('Proposals'):
        proposals_dir = ''
    else:
        proposals_dir = 'Proposals'

    return {
        'host': host,
        'port': port,
        'user': os.getenv('SFTP_SHARED_USER', '').strip(),
        'password': os.getenv('SFTP_SHARED_PASSWORD', ''),
        # Folder on the server; the proposals go in <SFTP_SHARED_REMOTE_DIR>/<SFTP_SHARED_PROPOSALS_DIR>,
        # by default /Proposals: the folder the Version_Control service reads (SFTP_BASE_PATH).
        'base_dir': base,
        'proposals_dir': proposals_dir,
    }


def shared_storage_dir() -> Path:
    """Local stand-in for the SFTP server (used when SFTP_SHARED_HOST is not set)."""
    return LOCAL_SHARED_DIR


def proposals_dir() -> Path:
    """Local folder with one subfolder per customer (layout: see services/proposals.py)."""
    return shared_storage_dir() / 'proposals'


def cors_origins() -> list[str]:
    """Browser origins allowed to call the API directly (comma-separated CORS_ORIGINS).

    Empty by default: in Kubernetes the frontend proxies /api/proposal/*, so no CORS is
    needed. For local frontend development set e.g. CORS_ORIGINS=http://localhost:5173.
    """
    _load_env()
    return [origin.strip() for origin in os.getenv('CORS_ORIGINS', '').split(',') if origin.strip()]


# ---------------------------------------------------------------------------
# Incoming uploads: the AI starts automatically for every complete upload in a
# subfolder of the source folder (see services/incoming_watcher.py). Local folder,
# NOT on the SFTP share. In Kubernetes the root filesystem is read-only: set
# INCOMING_DIR to a writable folder (for example /tmp/source).
# ---------------------------------------------------------------------------
LOCAL_INCOMING_DIR = SOURCE_DIR


def incoming_dir() -> Path:
    _load_env()
    value = os.getenv('INCOMING_DIR', '').strip()
    return Path(value) if value else LOCAL_INCOMING_DIR


def watch_incoming_enabled() -> bool:
    """WATCH_INCOMING=0 turns the automatic AI start off (default: on)."""
    _load_env()
    return os.getenv('WATCH_INCOMING', '1').strip().lower() not in {'0', 'false', 'no', 'off'}


def incoming_poll_seconds() -> float:
    """How often the incoming folder is checked (INCOMING_POLL_SECONDS, default 1)."""
    _load_env()
    try:
        return max(0.5, float(os.getenv('INCOMING_POLL_SECONDS', '1')))
    except ValueError:
        return 1.0


def ai_limit_targets() -> int:
    """Number of target fields the AI maps per upload (AI_LIMIT_TARGETS, default 10, 0 = all)."""
    _load_env()
    try:
        return max(0, int(os.getenv('AI_LIMIT_TARGETS', '10')))
    except ValueError:
        return 10
