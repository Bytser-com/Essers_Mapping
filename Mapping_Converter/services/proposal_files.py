"""Finding a proposal version on the shared storage and reading/writing its metadata.

Used by every converter step that works on an existing proposal (approving, returning,
building the mapping package, ...), so they all resolve folders and metadata the same way.

Layout (same as Mapping_Proposal and Version_Control):

    <customer>/v<N>/<proposal_type>/metadata.json   (or proposal.json)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from scripts.errors import ProposalConflictError, ProposalNotFoundError
from services.storage import StorageSession

# Same preference as Version_Control: metadata.json first, then proposal.json.
METADATA_FILES = ('metadata.json', 'proposal.json')
MAX_NAME_LENGTH = 20  # company and proposal type, same limit as Version_Control
_VERSION = re.compile(r'^v\d+$', re.IGNORECASE)


@dataclass(frozen=True)
class ProposalLocation:
    """One proposal version with the real folder names as they exist on the storage."""

    customer: str        # e.g. "nouryon"
    version: str         # e.g. "v1"
    proposal_type: str   # e.g. "inbound"
    metadata_path: str   # e.g. "nouryon/v1/inbound/metadata.json"

    @property
    def folder(self) -> str:
        return f'{self.customer}/{self.version}/{self.proposal_type}'


def validate_reference(company: str | None, version: str | None, proposal_type: str | None) -> tuple[str, str, str]:
    """Clean and check the request parameters; raises ValueError with a Dutch message."""
    company = _check_name(company, 'Bedrijf')
    proposal_type = _check_name(proposal_type, 'Proposaltype')
    version = (version or '').strip()
    if not _VERSION.fullmatch(version):
        raise ValueError('Versie moet de vorm v<nummer> hebben, bijvoorbeeld v1')
    return company, version, proposal_type


def find_proposal(s: StorageSession, company: str, version: str, proposal_type: str) -> ProposalLocation:
    """Locate a proposal version (case-insensitive). Raises ProposalNotFoundError."""
    customer_dir = _find_dir(s, '', company)
    if customer_dir is None:
        raise ProposalNotFoundError(f"Bedrijf '{company}' bestaat niet")
    version_dir = _find_dir(s, customer_dir, version)
    if version_dir is None:
        raise ProposalNotFoundError(f"Versie '{version}' bestaat niet voor '{customer_dir}'")
    type_dir = _find_dir(s, f'{customer_dir}/{version_dir}', proposal_type)
    if type_dir is None:
        raise ProposalNotFoundError(f"Proposaltype '{proposal_type}' bestaat niet voor '{customer_dir}/{version_dir}'")

    folder = f'{customer_dir}/{version_dir}/{type_dir}'
    for name in METADATA_FILES:
        if s.exists(f'{folder}/{name}'):
            return ProposalLocation(customer_dir, version_dir, type_dir, f'{folder}/{name}')
    raise ProposalNotFoundError(f"Geen metadata gevonden in '{folder}'")


def read_metadata(s: StorageSession, location: ProposalLocation) -> dict:
    """The metadata as a dict. Raises ProposalConflictError when it is not a valid JSON object."""
    path = location.metadata_path
    try:
        data = json.loads(s.read_text(path))
    except json.JSONDecodeError as error:
        raise ProposalConflictError(f"Metadata in '{path}' is geen geldige JSON") from error
    if not isinstance(data, dict):
        raise ProposalConflictError(f"Metadata in '{path}' is geen JSON-object")
    return data


def write_metadata(s: StorageSession, location: ProposalLocation, data: dict) -> None:
    """Write the metadata back (atomic on both storages)."""
    s.write_text(location.metadata_path, json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def _check_name(value: str | None, label: str) -> str:
    value = (value or '').strip()
    if not value:
        raise ValueError(f'{label} mag niet leeg zijn')
    if len(value) > MAX_NAME_LENGTH:
        raise ValueError(f'{label} mag maximaal {MAX_NAME_LENGTH} tekens bevatten')
    return value


def _find_dir(s: StorageSession, parent: str, name: str) -> str | None:
    wanted = name.casefold()
    return next((d for d in s.list_dirs(parent) if d.casefold() == wanted), None)
