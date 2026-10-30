"""Exceptions for the mapping tool."""
from __future__ import annotations


class MappingError(Exception):
    """Base class for every expected, user-facing error of the mapping tool."""


class ConfigError(MappingError):
    """Missing or invalid configuration, for example no Gemini API key."""


class InputDataError(MappingError):
    """Problems with the XML input folders or files."""


class StorageError(MappingError):
    """Problems connecting, creating folders, or writing to SFTP/local storage."""


class GeminiError(MappingError):
    """Gemini could not produce a response."""

    def __init__(self, message: str, code: int | str | None = None):
        super().__init__(message)
        self.code = code


class QuotaExceededError(GeminiError):
    """Gemini rate limit (429) or overload (503)."""
