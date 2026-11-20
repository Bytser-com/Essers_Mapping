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

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from scripts.errors import ProposalConflictError, ProposalNotFoundError, StorageError
from services.approval import approve_proposal
from services.storage import Storage, proposal_storage

logger = logging.getLogger(__name__)

router = APIRouter()


class ApproveRequest(BaseModel):
    description: str = ''


def get_proposal_storage() -> Storage:
    return proposal_storage()


# Documented in the OpenAPI schema (/docs); the frontend shows ``detail`` to the analyst.
ERROR_RESPONSES: dict[int | str, dict] = {
    400: {'description': 'Invalid input: too long description, invalid parameters'},
    404: {'description': 'Customer, version, proposal type or metadata not found'},
    409: {'description': 'Proposal cannot be approved in its current status (e.g. AI review running)'},
    502: {'description': 'The shared SFTP storage is not reachable'},
}


def trigger_ai_review(storage: Storage, company: str, version: str, proposal_type: str) -> dict | None:
    """Download the proposal's Excel file from storage and run the Gemini review."""
    from scripts.pipeline import run_review
    from services.proposal_files import find_proposal, read_metadata, write_metadata

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

        with storage.session() as s:
            location = find_proposal(s, company, version, proposal_type)
            meta = read_metadata(s, location)
            meta['ai_review'] = review_result
            if decision == 'REJECTED':
                meta['status'] = 'RETURNED'
                meta['ai_status'] = 'FAILED'
            else:
                meta['status'] = None
                meta['ai_status'] = None
            write_metadata(s, location, meta)
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
