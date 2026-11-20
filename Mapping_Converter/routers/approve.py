"""Approve endpoint for a reviewed mapping proposal (story IT2627T06-185).

POST /approve?company=<customer>&version=v<N>&proposalType=<type>
    body: {"description": "<what changed, max 200 characters>"}

Sets the proposal to AI_CHECKING_REVIEW ("AI-controle bezig"), stores the
description and answers immediately. The AI review and what follows (mapping
package or back to the analyst, story 187) then run in the background, see
services/finalization.py. The business rules live in services/; this route only
translates them to HTTP:

    400  invalid input (empty or too long description, invalid parameters)
    404  customer, version, proposal type or metadata not found
    409  proposal cannot be approved in its current status (e.g. AI review running)
    502  the shared SFTP storage is not reachable
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from routers.dependencies import get_packages_storage, get_proposal_storage
from scripts.errors import ProposalConflictError, ProposalNotFoundError, StorageError
from services.approval import approve_proposal
from services.finalization import finalize_in_background
from services.storage import Storage

logger = logging.getLogger(__name__)

router = APIRouter()


class ApproveRequest(BaseModel):
    description: str = ''


# Documented in the OpenAPI schema (/docs); the frontend shows ``detail`` to the analyst.
ERROR_RESPONSES: dict[int | str, dict] = {
    400: {'description': 'Invalid input: empty or too long description, invalid parameters'},
    404: {'description': 'Customer, version, proposal type or metadata not found'},
    409: {'description': 'Proposal cannot be approved in its current status (e.g. AI review running)'},
    502: {'description': 'The shared SFTP storage is not reachable'},
}


@router.post('/approve', responses=ERROR_RESPONSES)
def approve(
    request: ApproveRequest,
    background_tasks: BackgroundTasks,
    storage: Annotated[Storage, Depends(get_proposal_storage)],
    packages: Annotated[Storage, Depends(get_packages_storage)],
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
        # Do not log the request parameters: they are user input (log injection).
        logger.exception('Approving a proposal failed')
        raise HTTPException(status_code=502, detail='De bestanden zijn tijdelijk niet bereikbaar') from error

    logger.info('Proposal %s/%s/%s approved; AI review pending', result.company, result.version, result.proposal_type)
    # Runs after the response is sent: the analyst does not wait for Gemini.
    background_tasks.add_task(
        finalize_in_background, storage, packages, result.company, result.version, result.proposal_type,
    )
    return result.to_dict()
