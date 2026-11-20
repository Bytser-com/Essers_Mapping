"""Storage dependencies shared by the routers (FastAPI ``Depends``).

Tests replace them with a temporary folder via ``app.dependency_overrides``.
"""
from __future__ import annotations

from services.storage import Storage, packages_storage, proposal_storage


def get_proposal_storage() -> Storage:
    return proposal_storage()


def get_packages_storage() -> Storage:
    return packages_storage()
