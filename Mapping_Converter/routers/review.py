"""Review endpoint: Gemini AI quality gate for Excel mapping proposals.

POST /review-excel?companyName=<company>&type=<type>&versionNumber=<version>
POST /review        (hidden alias)

Retrieves the Excel proposal workbook from SFTP and sends extracted mapping rows
to the Gemini review agent.
"""
from __future__ import annotations

import logging
import sys
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

import sftp_service
from scripts.excel_review import InvalidWorkbook
from scripts.gemini_review import ReviewUnavailable
from scripts.pipeline import run_review
from sftp_service import (
    SftpError,
    SftpFileNotFoundError,
)

logger = logging.getLogger(__name__)

router = APIRouter()

REVIEW_RESPONSES: dict[int | str, dict] = {
    400: {"description": "Required parameters missing or empty."},
    404: {"description": "Excel proposal file not found on SFTP."},
    422: {"description": "Invalid or unsupported Excel workbook."},
    502: {"description": "SFTP storage error or connection failure."},
    503: {"description": "Excel AI review temporarily unavailable."},
}


def _get_downloader():
    """Resolve downloader from api module (if patched) or sftp_service directly."""
    api_mod = sys.modules.get("api")
    if api_mod and hasattr(api_mod, "download_proposal_excel_from_sftp"):
        return getattr(api_mod, "download_proposal_excel_from_sftp")
    return sftp_service.download_proposal_excel_from_sftp


@router.post(
    "/review-excel",
    responses=REVIEW_RESPONSES,
    summary="Review Excel mapping proposal consistency using Gemini AI",
)
@router.post(
    "/review",
    include_in_schema=False,
)
async def review_excel(
    companyName: Annotated[str, Query(..., description="Company / client name, e.g. nouryon")],
    type: Annotated[str, Query(..., description="Message / proposal type, e.g. inbound or outbound")],
    versionNumber: Annotated[str, Query(..., description="Version tag or number, e.g. v2 or 2")],
) -> dict:
    """Review Excel mapping consistency using Gemini by retrieving workbook from SFTP."""
    if not companyName or not companyName.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameter 'companyName' is required and cannot be empty.",
        )
    if not type or not type.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameter 'type' is required and cannot be empty.",
        )
    if not versionNumber or not versionNumber.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameter 'versionNumber' is required and cannot be empty.",
        )

    downloader = _get_downloader()
    try:
        contents, _sftp_path = downloader(
            company=companyName.strip(),
            version=versionNumber.strip(),
            proposal_type=type.strip(),
        )
    except SftpFileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except SftpError as error:
        logger.warning("SFTP error while retrieving proposal: %s", error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to retrieve proposal from SFTP: {error}",
        ) from error
    except Exception as error:
        logger.exception("Unexpected error while retrieving proposal from SFTP")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unexpected error retrieving proposal from SFTP: {error}",
        ) from error

    try:
        return run_review(contents)

    except InvalidWorkbook as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    except ReviewUnavailable as error:
        logger.warning("Excel review unavailable: %s", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    except Exception as error:
        logger.exception("Unexpected Excel AI review failure")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Excel AI review temporarily unavailable.",
        ) from error
