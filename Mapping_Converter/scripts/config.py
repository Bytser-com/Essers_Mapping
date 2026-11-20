"""Configuration for the Excel-only Gemini review service.

Locally reads the shared repository-root .env. In containers, environment
variables are normally injected by deployment configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

SERVICE_DIR = Path(__file__).resolve().parent.parent
REPOSITORY_DIR = SERVICE_DIR.parent
PROMPT_PATH = SERVICE_DIR / "review_prompt.txt"


@dataclass(frozen=True)
class ReviewSettings:
    api_key: str
    model: str
    timeout_ms: int = 60000


def load_review_settings() -> ReviewSettings:
    """Load shared .env without overriding values injected by the environment."""
    load_dotenv(REPOSITORY_DIR / ".env", override=False)
    model = (os.getenv("GEMINI_REVIEW_MODEL") or os.getenv("GEMINI_MODEL") or "").strip()

    timeout_ms = 60000
    timeout_sec = (os.getenv("GEMINI_REVIEW_TIMEOUT_SECONDS") or "").strip()
    if timeout_sec.isdigit():
        timeout_ms = int(timeout_sec) * 1000
    else:
        timeout_review_ms = (os.getenv("GEMINI_REVIEW_TIMEOUT_MS") or "").strip()
        if timeout_review_ms.isdigit():
            timeout_ms = int(timeout_review_ms)

    return ReviewSettings(
        api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        model=model,
        timeout_ms=timeout_ms,
    )
