"""Approve endpoint for a reviewed mapping proposal (story IT2627T06-185).

POST /approve?company=<customer>&version=v<N>&proposalType=<type>
    body: {"description": "<what changed, optional, max 200 characters>"}

Sets the proposal to AI_CHECKING_REVIEW ("AI-controle bezig"), stores the
description, and launches the AI review in the backend.

    400  invalid input (too long description, invalid parameters)
    404  customer, version, proposal type or metadata not found
    409  proposal cannot be approved in its current status (e.g. AI review running)
    502  the shared SFTP storage is not reachable
"""
from __future__ import annotations

import json
import logging
import re
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from scripts.errors import ProposalConflictError, ProposalNotFoundError, StorageError
from services.approval import approve_proposal
from services.proposal_files import METADATA_FILES, ProposalLocation, read_metadata, write_metadata
from services.statuses import ProposalStatus
from services.storage import Storage, packages_storage, proposal_storage

logger = logging.getLogger(__name__)

router = APIRouter()

_VERSION = re.compile(r'^v\d+$', re.IGNORECASE)
_active_reviews: set[tuple[str, str, str]] = set()


class ApproveRequest(BaseModel):
    description: str = ''


def get_proposal_storage() -> Storage:
    return proposal_storage()


def get_packages_storage() -> Storage:
    return packages_storage()


# Documented in the OpenAPI schema (/docs); the frontend shows ``detail`` to the analyst.
ERROR_RESPONSES: dict[int | str, dict] = {
    400: {'description': 'Invalid input: too long description, invalid parameters'},
    404: {'description': 'Customer, version, proposal type or metadata not found'},
    409: {'description': 'Proposal cannot be approved in its current status (e.g. AI review running)'},
    502: {'description': 'The shared SFTP storage is not reachable'},
}


def trigger_ai_review(
    storage: Storage,
    company: str,
    version: str,
    proposal_type: str,
    pkg_storage: Storage | None = None,
) -> dict | None:
    """Download the proposal's Excel file from storage, run the Gemini review,
    and if accepted by AI, convert the proposal to a mapping package on the packages storage.
    """
    from scripts.pipeline import run_review
    from services.proposal_files import find_proposal, read_metadata, write_metadata

    review_key = (company.strip().lower(), version.strip().lower(), proposal_type.strip().lower())
    _active_reviews.add(review_key)
    logger.info('Starting AI review for %s/%s/%s', company, version, proposal_type)
    try:
        contents = None
        with storage.session() as s:
            location = find_proposal(s, company, version, proposal_type)
            meta = read_metadata(s, location)
            filename = meta.get('filename')
            folder = location.folder
            if filename and s.exists(f'{folder}/{filename}'):
                contents = s.read_bytes(f'{folder}/{filename}')

        if contents is None:
            import sftp_service
            contents, _ = sftp_service.download_proposal_excel_from_sftp(company, version, proposal_type)

        review_result = run_review(contents)
        decision = review_result.get('decision', 'ACCEPTED')
        logger.info('AI review completed for %s/%s/%s: %s', company, version, proposal_type, decision)

        if decision == 'REJECTED':
            with storage.session() as s:
                location = find_proposal(s, company, version, proposal_type)
                meta = read_metadata(s, location)
                meta['ai_review'] = review_result
                meta['status'] = 'RETURNED'
                meta['ai_status'] = 'FAILED'
                write_metadata(s, location, meta)
        else:
            from services.packages import DEFAULT_USER, convert_excel_to_package, format_semver
            from services.proposal_files import delete_proposal_after_conversion

            if pkg_storage is None:
                pkg_storage = get_packages_storage()

            with storage.session() as s:
                location = find_proposal(s, company, version, proposal_type)
                meta = read_metadata(s, location)
                user_created = meta.get('uploadUser') or meta.get('upload_user') or meta.get('createdBy') or DEFAULT_USER
                package_ver = meta.get('package_version') or format_semver(version)

            _, sftp_path = convert_excel_to_package(
                pkg_storage,
                contents,
                company,
                version,
                proposal_type,
                user_created=user_created,
                package_version=package_ver,
            )
            logger.info('Proposal %s/%s/%s converted and saved to package: %s', company, version, proposal_type, sftp_path)

            with storage.session() as s:
                delete_proposal_after_conversion(s, company, version, proposal_type)

        return review_result

    except Exception as exc:
        logger.warning('AI review for %s/%s/%s did not complete: %s', company, version, proposal_type, exc)
        try:
            with storage.session() as s:
                location = find_proposal(s, company, version, proposal_type)
                meta = read_metadata(s, location)
                meta['ai_status'] = 'FAILED'
                meta['ai_review_error'] = str(exc)
                write_metadata(s, location, meta)
        except Exception:
            pass
        return None
    finally:
        _active_reviews.discard(review_key)


def find_stuck_proposals(
    storage: Storage,
    company: str | None = None,
    version: str | None = None,
    proposal_type: str | None = None,
) -> list[ProposalLocation]:
    company_filter = company.strip().lower() if company else None
    version_filter = version.strip().lower() if version else None
    type_filter = proposal_type.strip().lower() if proposal_type else None

    results: list[ProposalLocation] = []
    with storage.session() as s:
        try:
            customers = s.list_dirs('')
        except Exception as e:
            logger.warning('Failed to list root dirs on storage: %s', e)
            return []

        for cust in customers:
            if company_filter and cust.lower() != company_filter:
                continue
            try:
                versions = s.list_dirs(cust)
            except Exception:
                continue
            for ver in versions:
                if not _VERSION.fullmatch(ver):
                    continue
                if version_filter and ver.lower() != version_filter:
                    continue
                try:
                    types = s.list_dirs(f'{cust}/{ver}')
                except Exception:
                    continue
                for prop_t in types:
                    if type_filter and prop_t.lower() != type_filter:
                        continue
                    folder = f'{cust}/{ver}/{prop_t}'
                    meta_path = None
                    for name in METADATA_FILES:
                        if s.exists(f'{folder}/{name}'):
                            meta_path = f'{folder}/{name}'
                            break
                    if not meta_path:
                        continue
                    try:
                        meta = json.loads(s.read_text(meta_path))
                        if not isinstance(meta, dict):
                            continue
                    except Exception:
                        continue

                    # A proposal is stuck in AI review if status is AI_CHECKING_REVIEW
                    status = meta.get('status')
                    if status == ProposalStatus.AI_CHECKING_REVIEW.value or status == 'AI_CHECKING_REVIEW':
                        results.append(ProposalLocation(cust, ver, prop_t, meta_path))
    return results


@router.post('/ai-retry')
def ai_retry(
    background_tasks: BackgroundTasks,
    storage: Annotated[Storage, Depends(get_proposal_storage)],
    company: Annotated[str | None, Query()] = None,
    version: Annotated[str | None, Query()] = None,
    proposal_type: Annotated[str | None, Query(alias='proposalType')] = None,
) -> dict:
    """Restart stuck AI reviews for all proposals currently in AI_CHECKING_REVIEW."""
    stuck_locations = find_stuck_proposals(
        storage, company=company, version=version, proposal_type=proposal_type
    )
    retried = []

    for loc in stuck_locations:
        key = (loc.customer.lower(), loc.version.lower(), loc.proposal_type.lower())
        if key in _active_reviews:
            logger.info('Proposal %s/%s/%s is already actively reviewing; skipping retry enqueue.', loc.customer, loc.version, loc.proposal_type)
            continue

        try:
            with storage.session() as s:
                meta = read_metadata(s, loc)
                meta['ai_status'] = 'RUNNING'
                meta.pop('ai_review_error', None)
                write_metadata(s, loc, meta)

            background_tasks.add_task(trigger_ai_review, storage, loc.customer, loc.version, loc.proposal_type)
            retried.append({
                'company': loc.customer,
                'version': loc.version,
                'proposal_type': loc.proposal_type,
            })
            logger.info('Restarted AI review for stuck proposal %s/%s/%s', loc.customer, loc.version, loc.proposal_type)
        except Exception as e:
            logger.error('Failed to restart AI review for %s/%s/%s: %s', loc.customer, loc.version, loc.proposal_type, e)

    return {
        'status': 'ok',
        'retried_count': len(retried),
        'retried_proposals': retried,
    }


@router.post('/approve', responses=ERROR_RESPONSES)
def approve(
    request: ApproveRequest,
    background_tasks: BackgroundTasks,
    storage: Annotated[Storage, Depends(get_proposal_storage)],
    company: Annotated[str, Query()] = '',
    version: Annotated[str, Query()] = '',
    proposal_type: Annotated[str, Query(alias='proposalType')] = '',
) -> dict:
    try:
        result = approve_proposal(storage, company, version, proposal_type, request.description)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ProposalNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ProposalConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except StorageError as error:
        logger.exception('Approving a proposal failed')
        raise HTTPException(status_code=502, detail='De bestanden zijn tijdelijk niet bereikbaar') from error

    logger.info('Proposal %s/%s/%s approved; AI review scheduled', result.company, result.version, result.proposal_type)
    background_tasks.add_task(trigger_ai_review, storage, result.company, result.version, result.proposal_type)
    return result.to_dict()
