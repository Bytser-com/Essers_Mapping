"""Upload endpoint for customer XML files (user stories 48 and 60).

POST /upload  (multipart form)
    customer_name   the customer entered on the Home page
    files           one or more XML files of that customer

All files of one upload are stored together in a new folder in the source folder
(data/source/, or INCOMING_DIR), in the layout the incoming watcher expects:

    data/source/<YYYYMMDD-HHMMSS>_<customer>_<random>/
        order_1.xml, order_2.xml, ...
        upload.json          written LAST: {"customer": "Ostavel"}

As soon as upload.json is there, the watcher (services/incoming_watcher.py) starts the
AI for this upload and the proposal appears on Home with "AI maakt voorstel".
"""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from scripts.config import incoming_dir
from services.incoming_watcher import UPLOAD_MARKER
from services.proposals import customer_folder_name

router = APIRouter()


@router.post('/upload', status_code=201)
async def upload_xml(
    files: list[UploadFile] = File(...),
    customer_name: str = Form(''),
):
    customer = customer_name.strip()
    if not customer:
        raise HTTPException(status_code=400, detail='Upload mislukt: Vul eerst een klant in.')

    # Only keep the file name, so a name like "../x.xml" cannot leave the folder
    names = [Path(file.filename or '').name for file in files]
    if not names:
        raise HTTPException(status_code=400, detail='Upload mislukt: kies eerst een XML-bestand.')
    # Only XML files are allowed (same message as the frontend shows); nothing is stored otherwise
    if any(not name.lower().endswith('.xml') for name in names):
        raise HTTPException(status_code=400, detail='Upload mislukt: dit is geen XML-bestand.')

    # A new folder per upload, so the AI handles all files of this upload together
    upload_id = f'{datetime.now():%Y%m%d-%H%M%S}_{customer_folder_name(customer)}_{uuid.uuid4().hex[:6]}'
    folder = incoming_dir() / upload_id
    folder.mkdir(parents=True)
    for name, file in zip(names, files):
        (folder / name).write_bytes(await file.read())

    # upload.json LAST (written under another name first): only now the watcher picks it up
    temp = folder / f'.{UPLOAD_MARKER}.tmp'
    temp.write_text(json.dumps({'customer': customer}, ensure_ascii=False), encoding='utf-8')
    os.replace(temp, folder / UPLOAD_MARKER)

    return {'upload_id': upload_id, 'customer': customer, 'files': names}
