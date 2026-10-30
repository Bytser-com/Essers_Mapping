"""Upload endpoint for customer XML files and customer folder creation on SFTP."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..scripts.config import SOURCE_DIR
from ..scripts.errors import StorageError
from ..scripts.storage import save_customer_file

router = APIRouter()


@router.post('/upload', status_code=201)
async def upload_xml(
    file: UploadFile = File(...),
    customer_name: str = Form(default=''),
):
    clean_customer = customer_name.strip()
    if not clean_customer:
        raise HTTPException(status_code=400, detail='Vul eerst een klant in.')

    # Only keep the file name, so a name like "../x.xml" cannot leave the folder
    file_name = Path(file.filename or '').name

    # Only XML files are allowed (same message as the frontend shows)
    if not file_name.lower().endswith('.xml'):
        raise HTTPException(status_code=400, detail='Upload mislukt: dit is geen XML-bestand.')

    content = await file.read()

    # Save to customer folder on SFTP (or local fallback storage)
    try:
        storage_path = save_customer_file(clean_customer, file_name, content)
    except StorageError as exc:
        raise HTTPException(status_code=500, detail=f'Opslaan op SFTP mislukt: {exc}') from exc

    # Also keep a copy in data/source/ for the pipeline
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    (SOURCE_DIR / file_name).write_bytes(content)

    return {
        'file_name': file_name,
        'customer_name': clean_customer,
        'storage_path': storage_path,
    }
