"""Compatibility layer re-exporting models from scripts.models."""
from __future__ import annotations

from scripts.models import (
    MappingEntry,
    MappingPackage,
    PackageMeta,
    SavePackageResponse,
)

ALLOWED_EXTENSIONS = ('.xlsx', '.xls')
SaveToSftpResponse = SavePackageResponse

__all__ = [
    "ALLOWED_EXTENSIONS",
    "MappingEntry",
    "MappingPackage",
    "PackageMeta",
    "SavePackageResponse",
    "SaveToSftpResponse",
]
