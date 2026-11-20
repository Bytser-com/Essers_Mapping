"""Approve endpoint for a reviewed mapping proposal (story IT2627T06-185).

POST /approve?company=<customer>&version=v<N>&proposalType=<type>
    body: {"description": "<what changed, max 200 characters>"}

Sets the proposal to AI_CHECKING_REVIEW ("AI-controle bezig") and stores the
description. The business rules live in services/approval.py; this route only
translates them to HTTP:

    400  invalid input (empty or too long description, invalid parameters)
    404  customer, version, proposal type or metadata not found
    409  proposal cannot be approved in its current status (e.g. AI review running)
    502  the shared SFTP storage is not reachable
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
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


@router.post('/approve')
def approve(
    request: ApproveRequest,
    company: str = Query(''),
    version: str = Query(''),
    proposal_type: str = Query('', alias='proposalType'),
    storage: Storage = Depends(get_proposal_storage),
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
        logger.error('Approving %s/%s/%s failed: %s', company, version, proposal_type, error)
        raise HTTPException(status_code=502, detail='De bestanden zijn tijdelijk niet bereikbaar') from error

    logger.info('Proposal %s/%s/%s approved; AI review pending', result.company, result.version, result.proposal_type)
    return result.to_dict()
