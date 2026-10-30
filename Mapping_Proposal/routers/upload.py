"""Upload endpoint for customer XML files (user story 60).

POST /upload
    The frontend (Home page, "Interface uploaden") sends one XML file here.
    The file is saved in Mapping_Proposal/data/source/
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

# Same folder as SOURCE_DIR in scripts/config.py: Mapping_Proposal/data/source/
SOURCE_DIR = Path(__file__).resolve().parent.parent / 'data' / 'source'

router = APIRouter()


@router.post('/upload', status_code=201)
async def upload_xml(file: UploadFile):
    # Only keep the file name, so a name like "../x.xml" cannot leave the folder
    file_name = Path(file.filename or '').name

    # Only XML files are allowed (same message as the frontend shows)
    if not file_name.lower().endswith('.xml'):
        raise HTTPException(status_code=400, detail='Upload mislukt: dit is geen XML-bestand.')

    # Save the file in data/source/ so the pipeline can pick it up
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    (SOURCE_DIR / file_name).write_bytes(await file.read())

    return {'file_name': file_name}
