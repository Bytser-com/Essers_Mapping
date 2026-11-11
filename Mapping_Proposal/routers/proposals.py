import paramiko
from fastapi import APIRouter, HTTPException
from services import proposal_service

router = APIRouter(prefix="/proposals")

@router.get("/{company}", responses={404: {"description": "No proposal found for this company"}, 503: {"description": "SFTP server is unreachable"}})
def get_proposal(company: str):
    try:
        mappings, version, uploaded, edited = proposal_service.get_list_from_excel(company)
    except (paramiko.SSHException, OSError) as err:
        raise HTTPException(status_code=503, detail="...") from err
    if mappings is None:
        raise HTTPException(status_code=404, detail="No mappings found")
    return {
    "klant": company,
    "versie": version,
    "status": "In review" if edited else "Klaar om na te kijken",
    "geupload": uploaded,
    "mappings": mappings,
    }