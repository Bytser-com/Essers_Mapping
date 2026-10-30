"""Central configuration: project paths and settings from ``.env``.

``.env`` is read exactly once, here. Other modules call ``load_settings()``.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

# ai_tool/ folder (this file lives in ai_tool/scripts/).
ROOT = Path(__file__).resolve().parent.parent

# Fixed project locations. Change them here instead of in every script.

DATA_DIR = ROOT / 'data'
SOURCE_DIR = DATA_DIR / 'source'
HISTORICAL_DIR = DATA_DIR / 'historical'
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
