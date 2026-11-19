"""Mapping Converter API service: converts approved Excel proposals to JSON mapping packages."""

from fastapi import FastAPI, File, HTTPException, UploadFile, status

from converter import parse_mapping_excel
from models import MappingPackage

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
