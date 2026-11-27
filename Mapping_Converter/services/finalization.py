"""After approval: AI review, then mapping package or back to the analyst (story IT2627T06-187).

Started by routers/approve.py (``trigger_ai_review``) for a proposal with status
AI_CHECKING_REVIEW (set by services/approval.py):

    ACCEPTED   -> store MPackage.json as a new version (with the change description and
                  approval time), make that version the active version of the customer
                  and set the proposal to APPROVED ("Goedgekeurd")
    REJECTED   -> set the proposal to RETURNED with the AI findings (invalid workbook too)

When the review itself fails (Gemini unavailable, storage error, ...) the exception is
raised to the caller. The proposal then stays in AI_CHECKING_REVIEW, so POST /ai-retry
can start it again.

The package version is the proposal version: Mapping_Proposal already numbers a new
proposal as "latest package + 1" (v1 for a new customer). An existing package is never
overwritten.

Packages layout (packages storage, default /Packages), the same as Version_Control reads:

    <customer>/v<N>/<proposal_type>/MPackage.json
    <customer>/active.json      {"<proposal_type>": {"version": "v<N>", "updated_at", "updated_by"}}
"""
from __future__ import annotations

import json
import logging
import posixpath
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from scripts.errors import ProposalConflictError
from scripts.excel_review import InvalidWorkbook
from scripts.models import PackageMeta
from scripts.pipeline import run_review
from services.excel_converter import parse_mapping_excel
from services.packages import (
    DEFAULT_USER,
    build_package_path,
    format_semver,
    normalize_slug,
    remote_package_path,
)
from services.proposal_files import (
    ProposalLocation,
    find_proposal,
    find_workbook,
    read_metadata,
    validate_reference,
    write_metadata,
)
from services.statuses import ProposalStatus
from services.storage import Storage, StorageSession

logger = logging.getLogger(__name__)

ACTIVE_VERSION_FILE = 'active.json'
INVALID_WORKBOOK = 'Het Excel-bestand is ongeldig'

Review = Callable[[bytes], dict]


@dataclass(frozen=True)
class FinalizationResult:
    company: str
    version: str
    proposal_type: str
    status: str
    summary: str = ''
    findings: list[str] = field(default_factory=list)
    package_path: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class _Approved:
    """What was read from the proposal before the (slow) AI review."""

    location: ProposalLocation
    metadata: dict
    workbook: bytes
    package_path: str  # relative to the packages root


def finalize_proposal(
    proposals: Storage,
    packages: Storage,
    company: str,
    version: str,
    proposal_type: str,
    *,
    review: Review = run_review,
    now: datetime | None = None,
) -> FinalizationResult:
    """Run the AI review of an approved proposal and act on the decision.

    Raises ValueError (invalid parameters), ProposalNotFoundError, ProposalConflictError
    (wrong status or package already exists), StorageError, or whatever the review
    raises when it is unavailable (e.g. ReviewUnavailable).
    """
    approved = _load_approved(proposals, packages, *validate_reference(company, version, proposal_type))
    timestamp = (now or datetime.now(UTC)).isoformat(timespec='seconds')

    try:
        decision = review(approved.workbook)
    except InvalidWorkbook as error:
        decision = {'decision': 'REJECTED', 'summary': INVALID_WORKBOOK, 'findings': [str(error)]}

    if decision.get('decision') != 'ACCEPTED':  # fail closed: anything else is no acceptance
        return _return_to_analyst(proposals, approved, timestamp, decision)
    return _publish(proposals, packages, approved, timestamp, decision)


def _load_approved(proposals: Storage, packages: Storage, company: str, version: str,
                   proposal_type: str) -> _Approved:
    with proposals.session() as s:
        location = find_proposal(s, company, version, proposal_type)
        metadata = read_metadata(s, location)
        status = metadata.get('status')
        if status != ProposalStatus.AI_CHECKING_REVIEW:
            raise ProposalConflictError(f"Alleen een voorstel in AI-controle kan verwerkt worden, niet '{status}'")
        workbook = s.read_bytes(find_workbook(s, location, metadata))

    package_path = build_package_path(location.customer, location.version, location.proposal_type)
    with packages.session() as s:
        if s.exists(package_path):
            raise ProposalConflictError(f"Er bestaat al een mapping package voor '{location.folder}'")
    return _Approved(location, metadata, workbook, package_path)


def _publish(proposals: Storage, packages: Storage, approved: _Approved, timestamp: str,
             decision: dict) -> FinalizationResult:
    location, metadata = approved.location, approved.metadata
    user = metadata.get('approved_by') or DEFAULT_USER
    package = parse_mapping_excel(approved.workbook)
    package.meta = PackageMeta(
        client_name=normalize_slug(location.customer),
        package_version=format_semver(location.version),
        package_type=normalize_slug(location.proposal_type),
        date_created=timestamp,
        user_created=user,
        description=metadata.get('approval_description') or None,
        approved_at=metadata.get('approved_at'),
    )
    with packages.session() as s:
        s.make_dirs(posixpath.dirname(approved.package_path))
        s.write_text(approved.package_path, package.model_dump_json(indent=2))
        _activate(s, location, timestamp, user)

    full_path = remote_package_path(approved.package_path)
    _update_proposal(proposals, approved, timestamp, ProposalStatus.APPROVED, decision, ai_status=None,
                     package_path=full_path)
    logger.info('Proposal %s published as mapping package %s', location.folder, full_path)
    return _result(location, ProposalStatus.APPROVED, decision, full_path)


def _activate(s: StorageSession, location: ProposalLocation, timestamp: str, user: str) -> None:
    """Make the new version the active one for its type; other types keep theirs."""
    path = f'{normalize_slug(location.customer)}/{ACTIVE_VERSION_FILE}'
    active: dict = {}
    if s.exists(path):
        try:
            loaded = json.loads(s.read_text(path))
        except ValueError:
            logger.warning('Unreadable %s is replaced', path)
        else:
            if isinstance(loaded, dict):
                active = loaded
    active[normalize_slug(location.proposal_type)] = {
        'version': location.version.lower(),
        'updated_at': timestamp,
        'updated_by': user,
    }
    s.write_text(path, json.dumps(active, indent=2, ensure_ascii=False) + '\n')


def _return_to_analyst(proposals: Storage, approved: _Approved, timestamp: str,
                       decision: dict) -> FinalizationResult:
    _update_proposal(proposals, approved, timestamp, ProposalStatus.RETURNED, decision, ai_status='FAILED')
    return _result(approved.location, ProposalStatus.RETURNED, decision)


def _update_proposal(proposals: Storage, approved: _Approved, timestamp: str, status: ProposalStatus,
                     decision: dict, *, ai_status: str | None, package_path: str | None = None) -> None:
    data = {key: value for key, value in approved.metadata.items() if key != 'ai_review_error'}
    data.update({
        'status': status.value,
        'ai_status': ai_status,
        'ai_review': {**decision, 'checked_at': timestamp},
        'updated_at': timestamp,
    })
    if package_path:
        data['package_path'] = package_path
    with proposals.session() as s:
        write_metadata(s, approved.location, data)


def _result(location: ProposalLocation, status: ProposalStatus, decision: dict,
            package_path: str | None = None) -> FinalizationResult:
    return FinalizationResult(
        location.customer, location.version, location.proposal_type, status.value,
        str(decision.get('summary', '')), [str(item) for item in decision.get('findings') or []], package_path,
    )
