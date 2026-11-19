"""Upload endpoint for customer XML files (user stories 48 and 60).

POST /upload  (multipart form)
    customer_name   the customer entered on the Home page
    proposal_type   type of proposal (e.g. inbound, outbound, inboud-accept)
    files           one or more XML files of that customer

The metadata document is first created directly on the shared storage (SFTP server).
If storing the metadata on SFTP fails, an HTTP error is returned immediately and nothing
is stored locally.

Once the metadata document exists on SFTP, the uploaded files are stored together in a new
folder in the source folder (data/source/, or INCOMING_DIR):

    data/source/<YYYYMMDD-HHMMSS>_<customer>_<random>/
        order_1.xml, order_2.xml, ...
        proposal_ref.json    {"customer": "Ostavel", "version": 1, "folder": "ostavel/v1/inbound", "proposal_type": "inbound"}
        upload.json          written LAST: {"customer": "Ostavel", "proposal_type": "inbound"}

As soon as upload.json is there, the watcher (services/incoming_watcher.py) picks up the
existing proposal reference and runs the AI mapping.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from scripts.config import incoming_dir
from services.incoming_watcher import PROPOSAL_REF, UPLOAD_MARKER
from services.proposals import AiStatus, ProposalStatus, ProposalStore, customer_folder_name
from services.storage import proposal_storage

logger = logging.getLogger(__name__)

router = APIRouter()


def get_proposal_store() -> ProposalStore:
    return ProposalStore(proposal_storage())


@router.post('/upload', status_code=201)
async def upload_xml(
    files: list[UploadFile] = File(...),
    customer_name: str = Form(''),
    proposal_type: str | None = Form(None),
    store: ProposalStore = Depends(get_proposal_store),
):
    customer = customer_name.strip()
    if not customer:
        raise HTTPException(status_code=400, detail='Upload mislukt: Vul eerst een klant in.')

    prop_type = (proposal_type or '').strip().lower()
    if not prop_type:
        raise HTTPException(status_code=400, detail='Upload mislukt: proposal_type is verplicht (field is required).')

    # Only keep the file name, so a name like "../x.xml" cannot leave the folder
    names = [Path(file.filename or '').name for file in files]
    if not names:
        raise HTTPException(status_code=400, detail='Upload mislukt: kies eerst een XML-bestand.')
    # Only XML files are allowed (same message as the frontend shows); nothing is stored otherwise
    if any(not name.lower().endswith('.xml') for name in names):
        raise HTTPException(status_code=400, detail='Upload mislukt: dit is geen XML-bestand.')

    file_contents = [(name, await file.read()) for name, file in zip(names, files)]

    # Check on SFTP if a proposal folder already exists for this company (only 1 proposal per company allowed)
    try:
        if store.has_proposal(customer):
            raise HTTPException(
                status_code=400,
                detail=f'Upload mislukt: er is momenteel al een voorstel actief voor {customer}. Dit voorstel moet eerst afgerond worden.',
            )
    except HTTPException:
        raise
    except Exception as error:
        logger.error('Failed to check existing proposals on SFTP for %r: %s', customer, error)
        raise HTTPException(
            status_code=500,
            detail=f'Upload mislukt: kan metadata niet opslaan op SFTP server: {error}',
        )

    # First create the proposal metadata document on the SFTP storage.
    # If the SFTP server is unreachable or fails, return an error code instead of 200/201.
    try:
        ref = store.create_proposal(customer, proposal_type=prop_type)
    except Exception as error:
        logger.error('Failed to create proposal metadata on SFTP for %r: %s', customer, error)
        raise HTTPException(
            status_code=500,
            detail=f'Upload mislukt: kan metadata niet opslaan op SFTP server: {error}',
        )

    # A new folder per upload, so the AI handles all files of this upload together
    upload_id = f'{datetime.now():%Y%m%d-%H%M%S}_{customer_folder_name(customer)}_{uuid.uuid4().hex[:6]}'
    folder = incoming_dir() / upload_id
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for name, content in file_contents:
            (folder / name).write_bytes(content)

        # proposal_ref.json links this upload to the proposal already created on SFTP
        temp_ref = folder / f'.{PROPOSAL_REF}.tmp'
        temp_ref.write_text(
            json.dumps({'customer': ref.customer, 'version': ref.version, 'folder': ref.folder, 'proposal_type': ref.proposal_type}),
            encoding='utf-8',
        )
        os.replace(temp_ref, folder / PROPOSAL_REF)

        # upload.json LAST (written under another name first): only now the watcher picks it up
        temp = folder / f'.{UPLOAD_MARKER}.tmp'
        temp.write_text(json.dumps({'customer': customer, 'proposal_type': prop_type}, ensure_ascii=False), encoding='utf-8')
        os.replace(temp, folder / UPLOAD_MARKER)
    except Exception as error:
        shutil.rmtree(folder, ignore_errors=True)
        try:
            store.set_status(ref, ProposalStatus.AI_GENERATING, AiStatus.FAILED, error=f'Upload error: {error}'[:300])
        except Exception:
            pass
        logger.error('Failed to save uploaded files for upload %s: %s', upload_id, error)
        raise HTTPException(status_code=500, detail=f'Upload mislukt: {error}')

    return {'upload_id': upload_id, 'customer': customer, 'proposal_type': prop_type, 'files': names}


@router.post('/seed')
def seed(force: bool = False) -> dict:
    """Seed sample proposals into the storage (used for testing and dev)."""
    from scripts.dev_seed import seed_proposals
    try:
        seed_proposals(force=force)
        return {'status': 'ok', 'message': 'Proposals seeded successfully'}
    except Exception as e:
        logger.error('Failed to seed proposals: %s', e)
        raise HTTPException(status_code=500, detail=f'Seeding failed: {e}')
