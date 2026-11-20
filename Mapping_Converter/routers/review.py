"""AI consistency review of a stored proposal workbook (story 51).

POST /review-excel?company=<customer>&version=v<N>&proposalType=<type>

Reads the proposal's Excel workbook from the shared SFTP storage and asks Gemini
whether the mappings are internally consistent. Nothing is written. The logic lives
in services/review.py and scripts/; this route only translates it to HTTP:

    200  {"decision": "ACCEPTED" | "REJECTED", "summary", "findings", "checked_mappings"}
    400  invalid parameters
    404  customer, version, proposal type, metadata or workbook not found
    409  the proposal metadata is unreadable
    422  the workbook is not a valid mapping proposal
    502  the shared SFTP storage is not reachable
    503  the AI review is temporarily unavailable (never counts as an acceptance)
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from routers.approve import get_proposal_storage
from scripts.errors import ProposalConflictError, ProposalNotFoundError, StorageError
from scripts.excel_review import InvalidWorkbook
from scripts.gemini_review import ReviewUnavailable
from services.review import ProposalWorkbook, load_proposal_workbook, review_workbook
from services.storage import Storage

logger = logging.getLogger(__name__)

router = APIRouter()

REVIEW_UNAVAILABLE = 'De AI-controle is tijdelijk niet beschikbaar'

ERROR_RESPONSES: dict[int | str, dict] = {
    400: {'description': 'Invalid parameters'},
    404: {'description': 'Customer, version, proposal type, metadata or workbook not found'},
    409: {'description': 'The proposal metadata is unreadable'},
    422: {'description': 'Invalid or unsupported Excel workbook'},
    502: {'description': 'The shared SFTP storage is not reachable'},
    503: {'description': 'The AI review is temporarily unavailable'},
}


@router.post('/review-excel', responses=ERROR_RESPONSES)
@router.post('/review', include_in_schema=False)
def review_excel(
    storage: Annotated[Storage, Depends(get_proposal_storage)],
    company: Annotated[str, Query()] = '',
    version: Annotated[str, Query()] = '',
    proposal_type: Annotated[str, Query(alias='proposalType')] = '',
) -> dict:
    workbook = _load(storage, company, version, proposal_type)
    return _review(workbook)


def _load(storage: Storage, company: str, version: str, proposal_type: str) -> ProposalWorkbook:
    try:
        return load_proposal_workbook(storage, company, version, proposal_type)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ProposalNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ProposalConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except StorageError as error:
        # Do not log the request parameters: they are user input (log injection).
        logger.exception('Reading a proposal workbook failed')
        raise HTTPException(status_code=502, detail='De bestanden zijn tijdelijk niet bereikbaar') from error


def _review(workbook: ProposalWorkbook) -> dict:
    try:
        return review_workbook(workbook)
    except InvalidWorkbook as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ReviewUnavailable as error:
        logger.warning('AI review unavailable: %s', error)
        raise HTTPException(status_code=503, detail=REVIEW_UNAVAILABLE) from error
    except Exception as error:  # fail closed: an unexpected error is never an acceptance
        logger.exception('Unexpected AI review failure')
        raise HTTPException(status_code=503, detail=REVIEW_UNAVAILABLE) from error
