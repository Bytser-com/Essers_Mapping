"""Central configuration: project paths and settings from ``.env``.

``.env`` is read exactly once, here. Other modules call ``load_settings()`` or ``load_sftp_settings()``.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore

# Mapping_Proposal/ folder (this file lives in Mapping_Proposal/scripts/).
ROOT = Path(__file__).resolve().parent.parent

# Fixed project locations.
DATA_DIR = ROOT / 'data'
SOURCE_DIR = DATA_DIR / 'source'
HISTORICAL_DIR = DATA_DIR / 'historical'
OUTPUT_DIR = ROOT / 'output'
RUNS_DIR = OUTPUT_DIR / 'runs'
TEMPLATE_PATH = ROOT / 'templates' / 'mapping_template.xlsx'
PROMPT_PATH = ROOT / 'prompt.txt'
SFTP_STORAGE_DIR = DATA_DIR / 'sftp_storage'

DEFAULT_MODEL = 'gemini-3.5-flash-lite'

# Remembers whether .env was already read, so it is loaded only once per process.
_env_loaded = False


def _load_env() -> None:
    global _env_loaded
    if not _env_loaded:
        if load_dotenv:
            load_dotenv(ROOT / '.env')
        _env_loaded = True


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    gemini_timeout_ms: int


@dataclass(frozen=True)
class SFTPSettings:
    host: str
    port: int
    user: str
    password: str
    base_dir: str


def load_settings() -> Settings:
    """Read the current settings from the environment (after loading ``.env``)."""
    _load_env()
    try:
        timeout = int(os.getenv('GEMINI_TIMEOUT_MS', '120000'))
    except ValueError:
        timeout = 120000
    return Settings(
        gemini_api_key=os.getenv('GEMINI_API_KEY', '').strip(),
        gemini_model=os.getenv('GEMINI_MODEL', '').strip() or DEFAULT_MODEL,
        gemini_timeout_ms=timeout,
    )


def load_sftp_settings() -> SFTPSettings:
    """Read SFTP server connection settings from the environment."""
    _load_env()
    try:
        port = int(os.getenv('SFTP_PORT', '22'))
    except ValueError:
        port = 22

    return SFTPSettings(
        host=os.getenv('SFTP_HOST', '').strip(),
        port=port,
        user=os.getenv('SFTP_USER', '').strip(),
        password=os.getenv('SFTP_PASSWORD', '').strip(),
        base_dir=os.getenv('SFTP_BASE_DIR', 'customers').strip('/'),
    )
