"""Exceptions for the mapping tool.

The pipeline raises these instead of calling ``SystemExit``, so the same code can be
used from the command line and (later) from an API without stopping the process.
"""
from __future__ import annotations


# Hierarchy:
#   MappingError            -> catch this one to handle every expected tool error
#   ├── ConfigError         -> fix .env or the command-line options
#   ├── InputDataError      -> fix the files in data/
#   └── GeminiError         -> problem on Gemini's side
#       └── QuotaExceededError -> wait and rerun the same command (resumes)


class MappingError(Exception):
    """Base class for every expected, user-facing error of the mapping tool."""


class ConfigError(MappingError):
    """Missing or invalid configuration, for example no Gemini API key."""


class InputDataError(MappingError):
    """Problems with the XML input folders or files."""


class GeminiError(MappingError):
    """Gemini could not produce a response. ``code`` holds the HTTP status if known."""

    def __init__(self, message: str, code: int | str | None = None):
        super().__init__(message)
        self.code = code


class QuotaExceededError(GeminiError):
    """Gemini rate limit (429) or overload (503). Completed batches are kept."""
