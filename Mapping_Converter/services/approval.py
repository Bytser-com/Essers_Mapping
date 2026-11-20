"""Approving a reviewed mapping proposal (story IT2627T06-185).

The analyst approves a proposal with a short description of the change. The proposal
then waits for the AI review: status AI_CHECKING_REVIEW ("AI-controle bezig").
Running that AI review is NOT part of this module; a later step picks up proposals
with that status.

Layout on the shared storage (same as Mapping_Proposal and Version_Control):

    <customer>/v<N>/<proposal_type>/metadata.json   (or proposal.json)
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from scripts.errors import ProposalConflictError, ProposalNotFoundError
from services.storage import Storage, StorageSession

AI_CHECKING_REVIEW = 'AI_CHECKING_REVIEW'
# Statuses in which the analyst may approve. "In review" is what Version_Control writes
# after a reviewed Excel was uploaded again.
APPROVABLE_STATUSES = frozenset({'READY_FOR_REVIEW', 'IN_REVIEW', 'In review'})
# Same preference as Version_Control: metadata.json first, then proposal.json.
METADATA_FILES = ('metadata.json', 'proposal.json')

MAX_DESCRIPTION_LENGTH = 200
MAX_NAME_LENGTH = 20  # company and proposal type, same limit as Version_Control
_VERSION = re.compile(r'^v\d+$', re.IGNORECASE)


@dataclass(frozen=True)
class ApprovalResult:
    company: str
    version: str
    proposal_type: str
    status: str
    approval_description: str
    approved_at: str

    def to_dict(self) -> dict:
        return asdict(self)


def clean_description(description: str | None) -> str:
    """The change description without surrounding spaces; it must not be empty or too long."""
    text = (description or '').strip()
    if not text:
        raise ValueError('De omschrijving van de wijziging mag niet leeg zijn')
    if len(text) > MAX_DESCRIPTION_LENGTH:
        raise ValueError(f'De omschrijving mag maximaal {MAX_DESCRIPTION_LENGTH} tekens bevatten')
    return text


def approve_proposal(
    storage: Storage,
    company: str,
    version: str,
    proposal_type: str,
    description: str | None,
    *,
    now: datetime | None = None,
) -> ApprovalResult:
    """Approve the proposal and set it to AI_CHECKING_REVIEW.

    Raises ValueError for invalid input, ProposalNotFoundError when the proposal does
    not exist and ProposalConflictError when it cannot be approved in its current status.
    """
    company = _check_name(company, 'Bedrijf')
    proposal_type = _check_name(proposal_type, 'Proposaltype')
    version = (version or '').strip()
    if not _VERSION.fullmatch(version):
        raise ValueError('Versie moet de vorm v<nummer> hebben, bijvoorbeeld v1')
    text = clean_description(description)

    with storage.session() as s:
        folder = _resolve_folder(s, company, version, proposal_type)
        metadata_path = _find_metadata(s, folder)
        data = _read_json(s, metadata_path)

        status = data.get('status')
        if status == AI_CHECKING_REVIEW:
            raise ProposalConflictError('De AI-controle is al bezig; dit voorstel kan niet opnieuw goedgekeurd worden')
        if status not in APPROVABLE_STATUSES:
            raise ProposalConflictError(f"Een voorstel met status '{status}' kan niet goedgekeurd worden")

        approved_at = (now or datetime.now(UTC)).isoformat(timespec='seconds')
        data.update({
            'status': AI_CHECKING_REVIEW,
            'approval_description': text,
            'approved_at': approved_at,
            'updated_at': approved_at,
        })
        s.write_text(metadata_path, json.dumps(data, indent=2, ensure_ascii=False) + '\n')

    customer_dir, version_dir, type_dir = folder.split('/')
    return ApprovalResult(
        company=customer_dir,
        version=version_dir,
        proposal_type=type_dir,
        status=AI_CHECKING_REVIEW,
        approval_description=text,
        approved_at=approved_at,
    )


def _check_name(value: str | None, label: str) -> str:
    value = (value or '').strip()
    if not value:
        raise ValueError(f'{label} mag niet leeg zijn')
    if len(value) > MAX_NAME_LENGTH:
        raise ValueError(f'{label} mag maximaal {MAX_NAME_LENGTH} tekens bevatten')
    return value


def _resolve_folder(s: StorageSession, company: str, version: str, proposal_type: str) -> str:
    """'<customer>/v<N>/<type>' with the real folder names (case-insensitive lookup)."""
    customer_dir = _find_dir(s, '', company)
    if customer_dir is None:
        raise ProposalNotFoundError(f"Bedrijf '{company}' bestaat niet")
    version_dir = _find_dir(s, customer_dir, version)
    if version_dir is None:
        raise ProposalNotFoundError(f"Versie '{version}' bestaat niet voor '{customer_dir}'")
    type_dir = _find_dir(s, f'{customer_dir}/{version_dir}', proposal_type)
    if type_dir is None:
        raise ProposalNotFoundError(f"Proposaltype '{proposal_type}' bestaat niet voor '{customer_dir}/{version_dir}'")
    return f'{customer_dir}/{version_dir}/{type_dir}'


def _find_dir(s: StorageSession, parent: str, name: str) -> str | None:
    wanted = name.casefold()
    return next((d for d in s.list_dirs(parent) if d.casefold() == wanted), None)


def _find_metadata(s: StorageSession, folder: str) -> str:
    for name in METADATA_FILES:
        path = f'{folder}/{name}'
        if s.exists(path):
            return path
    raise ProposalNotFoundError(f"Geen metadata gevonden in '{folder}'")


def _read_json(s: StorageSession, path: str) -> dict:
    try:
        data = json.loads(s.read_text(path))
    except json.JSONDecodeError as error:
        raise ProposalConflictError(f"Metadata in '{path}' is geen geldige JSON") from error
    if not isinstance(data, dict):
        raise ProposalConflictError(f"Metadata in '{path}' is geen JSON-object")
    return data
