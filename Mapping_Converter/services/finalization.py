"""After approval: AI review, then mapping package or back to the analyst (story IT2627T06-187).

Picks up one proposal with status AI_CHECKING_REVIEW (set by services/approval.py) and:

    ACCEPTED   -> store MPackage.json as a new version (with the change description and
                  approval time), make that version the customer's active version and set
                  the proposal to APPROVED ("Goedgekeurd")
    REJECTED   -> set the proposal to RETURNED with the findings (invalid workbook too)
    no review  -> back to IN_REVIEW with an error, so the analyst can approve again

The package version is the proposal version: Mapping_Proposal already numbers a new
proposal as "latest package + 1" (v1 for a new customer). An existing package is never
overwritten.

Packages layout (packages storage, default /Packages):

    <customer>/v<N>/<proposal_type>/MPackage.json
    <customer>/active.json      {"active_version": "v<N>", ...}
"""
from __future__ import annotations

import json
import logging
import posixpath
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from scripts.errors import ProposalConflictError
from scripts.excel_review import InvalidWorkbook
from scripts.models import PackageMeta
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
from services.review import ProposalWorkbook, review_workbook
from services.statuses import ProposalStatus
from services.storage import Storage

logger = logging.getLogger(__name__)

ACTIVE_VERSION_FILE = 'active.json'
REVIEW_UNAVAILABLE = 'De AI-controle was niet beschikbaar. Keur het voorstel opnieuw goed.'


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
    workbook: ProposalWorkbook
    package_path: str  # relative to the packages root


def finalize_proposal(
    proposals: Storage,
    packages: Storage,
    company: str,
    version: str,
    proposal_type: str,
    *,
    review=review_workbook,
    now: datetime | None = None,
) -> FinalizationResult:
    """Run the AI review of an approved proposal and act on the decision.

    Raises ValueError (invalid parameters), ProposalNotFoundError, ProposalConflictError
    (wrong status or package already exists) or StorageError.
    """
    approved = _load_approved(proposals, packages, *validate_reference(company, version, proposal_type))
    timestamp = (now or datetime.now(UTC)).isoformat(timespec='seconds')

    try:
        decision = review(approved.workbook)
    except InvalidWorkbook as error:
        return _return_to_analyst(proposals, approved, timestamp, 'Het Excel-bestand is ongeldig', [str(error)])
    except Exception:  # fail closed: without a review there is no package
        logger.exception('AI review failed for %s', approved.location.folder)
        return _back_in_review(proposals, approved, timestamp)

    summary = str(decision.get('summary', ''))
    findings = [str(item) for item in decision.get('findings') or []]
    if decision.get('decision') != 'ACCEPTED':
        return _return_to_analyst(proposals, approved, timestamp, summary, findings)
    return _publish(proposals, packages, approved, timestamp, summary, findings)


def finalize_in_background(proposals: Storage, packages: Storage, company: str, version: str,
                           proposal_type: str) -> None:
    """Background task started by POST /approve. Never raises: nobody would see the error."""
    try:
        result = finalize_proposal(proposals, packages, company, version, proposal_type)
    except Exception:
        logger.exception('Processing an approved proposal failed')
        return
    logger.info('Approved proposal %s/%s/%s processed: %s',
                result.company, result.version, result.proposal_type, result.status)


def _load_approved(proposals: Storage, packages: Storage, company: str, version: str,
                   proposal_type: str) -> _Approved:
    with proposals.session() as s:
        location = find_proposal(s, company, version, proposal_type)
        metadata = read_metadata(s, location)
        status = metadata.get('status')
        if status != ProposalStatus.AI_CHECKING_REVIEW:
            raise ProposalConflictError(f"Alleen een voorstel in AI-controle kan verwerkt worden, niet '{status}'")
        path = find_workbook(s, location, metadata)
        workbook = ProposalWorkbook(path, s.read_bytes(path))

    package_path = build_package_path(location.customer, location.version, location.proposal_type)
    with packages.session() as s:
        if s.exists(package_path):
            raise ProposalConflictError(f"Er bestaat al een mapping package voor '{location.folder}'")
    return _Approved(location, metadata, workbook, package_path)


def _publish(proposals: Storage, packages: Storage, approved: _Approved, timestamp: str,
             summary: str, findings: list[str]) -> FinalizationResult:
    location, metadata = approved.location, approved.metadata
    package = parse_mapping_excel(approved.workbook.contents)
    package.meta = PackageMeta(
        client_name=normalize_slug(location.customer),
        package_version=format_semver(location.version),
        package_type=normalize_slug(location.proposal_type),
        date_created=timestamp,
        user_created=metadata.get('approved_by') or DEFAULT_USER,
        description=metadata.get('approval_description'),
        approved_at=metadata.get('approved_at'),
    )
    active = {
        'active_version': location.version,
        'proposal_type': normalize_slug(location.proposal_type),
        'description': metadata.get('approval_description'),
        'activated_at': timestamp,
    }
    with packages.session() as s:
        s.make_dirs(posixpath.dirname(approved.package_path))
        s.write_text(approved.package_path, package.model_dump_json(indent=2))
        s.write_text(f'{normalize_slug(location.customer)}/{ACTIVE_VERSION_FILE}',
                     json.dumps(active, indent=2, ensure_ascii=False) + '\n')

    full_path = remote_package_path(approved.package_path)
    _update_proposal(proposals, location, metadata, timestamp, ProposalStatus.APPROVED, {
        'ai_review': _review_record('ACCEPTED', summary, findings, timestamp),
        'package_path': full_path,
    })
    return _result(location, ProposalStatus.APPROVED, summary, findings, full_path)


def _return_to_analyst(proposals: Storage, approved: _Approved, timestamp: str,
                       summary: str, findings: list[str]) -> FinalizationResult:
    _update_proposal(proposals, approved.location, approved.metadata, timestamp, ProposalStatus.RETURNED, {
        'ai_review': _review_record('REJECTED', summary, findings, timestamp),
    })
    return _result(approved.location, ProposalStatus.RETURNED, summary, findings)


def _back_in_review(proposals: Storage, approved: _Approved, timestamp: str) -> FinalizationResult:
    _update_proposal(proposals, approved.location, approved.metadata, timestamp, ProposalStatus.IN_REVIEW, {
        'ai_review_error': REVIEW_UNAVAILABLE,
    })
    return _result(approved.location, ProposalStatus.IN_REVIEW, REVIEW_UNAVAILABLE)


def _update_proposal(proposals: Storage, location: ProposalLocation, metadata: dict, timestamp: str,
                     status: ProposalStatus, extra: dict) -> None:
    data = {key: value for key, value in metadata.items() if key != 'ai_review_error'}
    data.update(extra)
    data.update({'status': status.value, 'updated_at': timestamp})
    with proposals.session() as s:
        write_metadata(s, location, data)


def _review_record(decision: str, summary: str, findings: list[str], timestamp: str) -> dict:
    return {'decision': decision, 'summary': summary, 'findings': findings, 'checked_at': timestamp}


def _result(location: ProposalLocation, status: ProposalStatus, summary: str = '',
            findings: list[str] | None = None, package_path: str | None = None) -> FinalizationResult:
    return FinalizationResult(location.customer, location.version, location.proposal_type, status.value,
                              summary, list(findings or []), package_path)
