"""Mapping Converter API with an Excel-only Gemini consistency review endpoint."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile

from scripts.excel_review import InvalidWorkbook
from scripts.gemini_review import ReviewUnavailable
from scripts.pipeline import run_review

logger = logging.getLogger(__name__)
app = FastAPI(title='Mapping Converter', version='1.1.0')


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'mapping-converter'}


@app.get('/')
def root():
    return {'message': 'Mapping Converter Service (placeholder)'}


@app.post(
    '/review-excel',
    responses={
        400: {'description': 'Uploaded file must be an .xlsx workbook.'},
        422: {'description': 'Invalid or unsupported Excel workbook.'},
        503: {'description': 'Excel AI review temporarily unavailable.'},
    },
)
async def review_excel(file: Annotated[UploadFile, File()]) -> dict:
    if not (file.filename or '').lower().endswith('.xlsx'):
        raise HTTPException(
            status_code=400,
            detail='Please upload a .xlsx workbook.',
        )

    # Read with an upper bound, not an unlimited UploadFile.read().
    contents = await file.read(5 * 1024 * 1024 + 1)

    try:
        return run_review(contents)

    except InvalidWorkbook as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    except ReviewUnavailable as error:
        logger.warning('Excel review unavailable: %s', error)
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error

    except Exception as error:
        logger.exception('Unexpected Excel AI review failure')
        raise HTTPException(
            status_code=503,
            detail='Excel AI review temporarily unavailable.',
        ) from error
