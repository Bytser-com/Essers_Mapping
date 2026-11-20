"""Mapping Converter API service: converts approved Excel proposals to JSON mapping packages."""

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

app = FastAPI(title="Mapping Converter Service", version="1.0.0")

ALLOWED_EXTENSIONS = {".xlsx", ".xls"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "mapping-converter"}


@app.get("/")
def root():
    return {"message": "Mapping Converter Service"}


@app.post(
    "/convert",
    response_model=MappingPackage,
    status_code=status.HTTP_200_OK,
    summary="Convert an Excel mapping proposal into a JSON mapping package",
)
async def convert_mapping_proposal(file: UploadFile = File(...)) -> MappingPackage:
    """Accept an uploaded Excel mapping proposal (.xlsx) and extract source-target paths into JSON."""
    filename = (file.filename or "").lower()
    if not any(filename.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only Excel files (.xlsx, .xls) are accepted.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    try:
        package = parse_mapping_excel(content)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse Excel workbook: {exc}",
        ) from exc

    return package


@app.post(
    "/convert-and-upload",
    response_model=SaveToSftpResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Convert Excel proposal and upload the JSON package directly to SFTP",
)
@app.post(
    "/convert/save",
    response_model=SaveToSftpResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def convert_and_upload_proposal(
    file: UploadFile = File(...),
    company: str = Form(..., description="Company / client name, e.g. nouryon"),
    version: str = Form(..., description="Version tag, e.g. v3, v4, or 1.0.0"),
    message_type: str = Form(..., description="Message type, e.g. inbound or outbound"),
    user_created: str = Form("analist_a", description="Author or analyst identifier"),
    package_version: str | None = Form(None, description="Optional semantic version override, e.g. 1.0.0"),
) -> SaveToSftpResponse:
    """Convert an approved Excel workbook to JSON and write MPackage.json to the SFTP server.

    SFTP path pattern:
        /Packages/<company>/<version>/<message_type>/MPackage.json
        (e.g. /Packages/nouryon/v4/outbound/MPackage.json)
    """
    if not company.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bedrijfsnaam (company) is verplicht.")
    if not str(version).strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Versie (version) is verplicht.")
    if not message_type.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Berichttype (message_type) is verplicht.")

    fname = (file.filename or "").lower()
    if not any(fname.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only Excel files (.xlsx, .xls) are accepted.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    try:
        package = parse_mapping_excel(content)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse Excel workbook: {exc}",
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
            detail=f"Onverwachte fout tijdens opslaan op SFTP: {exc}",
        ) from exc

    cfg = get_sftp_config()
    server_info = f"{cfg.host}:{cfg.port}" if cfg.host not in ("none", "local", "offline") else "local-filesystem"

    return SaveToSftpResponse(
        status="success",
        sftp_path=sftp_path,
        sftp_server=server_info,
        company=normalize_slug(company),
        version=normalize_version(version),
        message_type=normalize_slug(message_type),
        filename="MPackage.json",
        mapping_count=len(package.mappings),
        package=package,
    )
