
"""Mapping Converter API: Gemini review and Excel-to-JSON conversion."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status

from converter import parse_mapping_excel
from models import MappingPackage, SaveToSftpResponse
from sftp_service import (
    SftpError,
    get_sftp_config,
    normalize_slug,
    normalize_version,
    save_mapping_package_to_sftp,
)

from scripts.excel_review import InvalidWorkbook
from scripts.gemini_review import ReviewUnavailable
from scripts.pipeline import run_review

logger = logging.getLogger(__name__)
app = FastAPI(title='Mapping Converter Service', version='1.1.0')

ALLOWED_EXTENSIONS = {'.xlsx', '.xls'}


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'mapping-converter'}


@app.get('/')
def root():
    return {'message': 'Mapping Converter Service'}


@app.post(
    '/review-excel',
    responses={
        400: {'description': 'Uploaded file must be an .xlsx workbook.'},
        422: {'description': 'Invalid or unsupported Excel workbook.'},
        503: {'description': 'Excel AI review temporarily unavailable.'},
    },
)
async def review_excel(
    file: Annotated[UploadFile, File()],
) -> dict:
    """Review Excel mapping consistency using Gemini."""
    if not (file.filename or '').lower().endswith('.xlsx'):
        raise HTTPException(
            status_code=400,
            detail='Please upload a .xlsx workbook.',
        )

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


@app.post(
    '/convert',
    status_code=status.HTTP_200_OK,
    summary='Convert an Excel mapping proposal into a JSON mapping package',
)
async def convert_mapping_proposal(
    file: UploadFile = File(...),
) -> MappingPackage:
    """Convert an uploaded Excel mapping proposal to JSON."""
    filename = (file.filename or '').lower()

    if not any(filename.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Invalid file format. Only Excel files (.xlsx, .xls) are accepted.',
        )

    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Uploaded file is empty.',
        )

    try:
        package = parse_mapping_excel(content)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Failed to parse Excel workbook: {exc}',
        ) from exc

    return package


@app.post(
    '/convert-and-upload',
    status_code=status.HTTP_201_CREATED,
    summary='Convert Excel proposal and upload the JSON package directly to SFTP',
)
@app.post(
    '/convert/save',
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def convert_and_upload_proposal(
    file: UploadFile = File(...),
    company: str = Form(..., description='Company / client name, e.g. nouryon'),
    version: str = Form(..., description='Version tag, e.g. v3, v4, or 1.0.0'),
    message_type: str = Form(..., description='Message type, e.g. inbound or outbound'),
    user_created: str = Form('analist_a', description='Author or analyst identifier'),
    package_version: str | None = Form(
        None,
        description='Optional semantic version override, e.g. 1.0.0',
    ),
) -> SaveToSftpResponse:
    """Convert Excel to JSON and upload the mapping package to SFTP."""
    if not company.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Bedrijfsnaam (company) is verplicht.',
        )

    if not str(version).strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Versie (version) is verplicht.',
        )

    if not message_type.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Berichttype (message_type) is verplicht.',
        )

    fname = (file.filename or '').lower()

    if not any(fname.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Invalid file format. Only Excel files (.xlsx, .xls) are accepted.',
        )

    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Uploaded file is empty.',
        )

    try:
        package = parse_mapping_excel(content)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Failed to parse Excel workbook: {exc}',
        ) from exc

    try:
        sftp_path = save_mapping_package_to_sftp(
            package=package,
            company=company,
            version=version,
            message_type=message_type,
            user_created=user_created,
            package_version=package_version,
        )

    except SftpError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Onverwachte fout tijdens opslaan op SFTP: {exc}',
        ) from exc

    cfg = get_sftp_config()
    server_info = (
        f'{cfg.host}:{cfg.port}'
        if cfg.host not in ('none', 'local', 'offline')
        else 'local-filesystem'
    )

    return SaveToSftpResponse(
        status='success',
        sftp_path=sftp_path,
        sftp_server=server_info,
        company=normalize_slug(company),
        version=normalize_version(version),
        message_type=normalize_slug(message_type),
        filename='MPackage.json',
        mapping_count=len(package.mappings),
        package=package,
    )
