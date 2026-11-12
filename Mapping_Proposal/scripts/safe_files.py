"""Bound file paths and replace files atomically without predictable temp names."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile


def confined_path(root: Path, path: Path) -> Path:
    """Resolve symlinks and reject destinations outside the configured directory."""
    root = root.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ValueError('File path leaves its configured directory.')
    return target


@contextmanager
def atomic_writer(target: Path, *, binary: bool = False):
    """Close a unique temporary file before replacing the destination, also on Windows."""
    temporary = NamedTemporaryFile(
        mode='wb' if binary else 'w',
        encoding=None if binary else 'utf-8',
        dir=target.parent, prefix=f'.{target.name}.', suffix='.tmp', delete=False,
    )
    temporary_path = Path(temporary.name)
    try:
        with temporary as handle:
            yield handle
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)
