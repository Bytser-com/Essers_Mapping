"""Approving a reviewed mapping proposal (story IT2627T06-185).

The analyst approves a proposal with a short description of the change. The proposal
then waits for the AI review: status AI_CHECKING_REVIEW ("AI-controle bezig").
Running that AI review is NOT part of this module; a later step picks up proposals
with that status.

Finding the proposal and reading/writing its metadata: services/proposal_files.py.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from scripts.errors import ProposalConflictError
from services.proposal_files import find_proposal, read_metadata, validate_reference, write_metadata
from services.statuses import APPROVABLE_STATUSES, ProposalStatus
from services.storage import Storage

MAX_DESCRIPTION_LENGTH = 200


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
    """The change description without surrounding spaces; optional, max 200 characters."""
    text = (description or '').strip()
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
    company, version, proposal_type = validate_reference(company, version, proposal_type)
    text = clean_description(description)

    with storage.session() as s:
        location = find_proposal(s, company, version, proposal_type)
        data = read_metadata(s, location)

        status = data.get('status')
        if status == ProposalStatus.AI_CHECKING_REVIEW:
            raise ProposalConflictError('De AI-controle is al bezig; dit voorstel kan niet opnieuw goedgekeurd worden')
        if status not in APPROVABLE_STATUSES:
            raise ProposalConflictError(f"Een voorstel met status '{status}' kan niet goedgekeurd worden")

        approved_at = (now or datetime.now(UTC)).isoformat(timespec='seconds')
        data.pop('ai_review_error', None)
        data.update({
            'status': ProposalStatus.AI_CHECKING_REVIEW.value,
            'ai_status': 'RUNNING',  # Home refreshes while the AI is busy (frontend ProposalOverview)
            'approval_description': text,
            'approved_at': approved_at,
            'updated_at': approved_at,
        })
        write_metadata(s, location, data)

    return ApprovalResult(
        company=location.customer,
        version=location.version,
        proposal_type=location.proposal_type,
        status=ProposalStatus.AI_CHECKING_REVIEW.value,
        approval_description=text,
        approved_at=approved_at,
    )
