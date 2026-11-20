"""Convert endpoints: Excel mapping proposal -> JSON mapping package (story 54).

POST /convert               multipart 'file': returns the JSON package (preview, nothing stored)
POST /convert-and-upload    multipart 'file' + form fields: stores MPackage.json on the shared storage
                            (/convert/save is kept as a hidden alias)

The parsing and storing live in services/excel_converter.py and services/packages.py; this
route only checks the upload and translates errors to HTTP:

    400  not an Excel file, empty file, workbook cannot be read, or missing form fields
    502  the shared SFTP storage is not reachable
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from scripts.errors import StorageError
from scripts.models import MappingPackage, SavePackageResponse
from services.excel_converter import parse_mapping_excel
from services.packages import (
    DEFAULT_USER,
    PACKAGE_FILENAME,
    describe_packages_server,
    normalize_slug,
    normalize_version,
    save_mapping_package,
)
from services.storage import Storage, packages_storage

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_EXTENSIONS = ('.xlsx', '.xls')

PREVIEW_RESPONSES: dict[int | str, dict] = {
    400: {'description': 'Not an Excel file, empty file or workbook cannot be read'},
}
UPLOAD_RESPONSES: dict[int | str, dict] = {
    400: {'description': 'Not an Excel file, empty file, workbook cannot be read or missing form fields'},
    502: {'description': 'The shared SFTP storage is not reachable'},
}


def get_packages_storage() -> Storage:
    return packages_storage()


@router.post('/convert', summary='Convert an Excel mapping proposal into a JSON mapping package',
             responses=PREVIEW_RESPONSES)
async def convert_mapping_proposal(file: Annotated[UploadFile, File()]) -> MappingPackage:
    """Accept an uploaded Excel mapping proposal and return the extracted source-target paths."""
    return _parse_upload(file.filename, await file.read())


@router.post('/convert-and-upload', status_code=status.HTTP_201_CREATED, responses=UPLOAD_RESPONSES,
             summary='Convert an Excel proposal and store the JSON package on the shared storage')
@router.post('/convert/save', status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def convert_and_upload_proposal(
    file: Annotated[UploadFile, File()],
    storage: Annotated[Storage, Depends(get_packages_storage)],
    company: Annotated[str, Form(description='Company / client name, e.g. nouryon')],
    version: Annotated[str, Form(description='Version tag, e.g. v3, v4 or 1.0.0')],
    proposal_type: Annotated[str, Form(description='Proposal type, e.g. inbound or outbound')],
    user_created: Annotated[str, Form(description='Author or analyst identifier')] = DEFAULT_USER,
    package_version: Annotated[str | None, Form(description='Optional semantic version, e.g. 1.0.0')] = None,
) -> SavePackageResponse:
    """Convert an Excel workbook to JSON and write MPackage.json to the shared storage.

    Path: /Packages/<company>/<version>/<proposal_type>/MPackage.json
    """
    _require(company, 'Bedrijfsnaam (company) is verplicht.')
    _require(version, 'Versie (version) is verplicht.')
    _require(proposal_type, 'Proposaltype (proposal_type) is verplicht.')
    package = _parse_upload(file.filename, await file.read())

    try:
        sftp_path = save_mapping_package(storage, package, company, version, proposal_type,
                                         user_created=user_created, package_version=package_version)
    except StorageError as error:
        logger.exception('Storing a mapping package failed')
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail='De bestanden zijn tijdelijk niet bereikbaar') from error

    return SavePackageResponse(
        sftp_path=sftp_path,
        sftp_server=describe_packages_server(),
        company=normalize_slug(company),
        version=normalize_version(version),
        proposal_type=normalize_slug(proposal_type),
        filename=PACKAGE_FILENAME,
        mapping_count=len(package.mappings),
        package=package,
    )


def _require(value: str, message: str) -> None:
    if not value.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _parse_upload(filename: str | None, content: bytes) -> MappingPackage:
    """Check the uploaded file and parse it; raises HTTPException 400 when it cannot be used."""
    if not (filename or '').lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='Invalid file format. Only Excel files (.xlsx, .xls) are accepted.')
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Uploaded file is empty.')
    try:
        return parse_mapping_excel(content)
    except Exception as error:  # openpyxl raises many different errors for unreadable files
        logger.exception('Parsing an uploaded Excel workbook failed')
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='Failed to parse Excel workbook.') from error
