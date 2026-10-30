from fastapi import APIRouter, HTTPException
from services import proposal_service

router = APIRouter(prefix="/proposals")

@router.get("/{company}")
def get_proposal(company: str):
    mappings, version, uploaded, edited = proposal_service.get_list_from_excel(company)
    if mappings is None:
        raise HTTPException(status_code=404, detail="No mappings found")
    return {
    "klant": company,
    "versie": version,
    "status": "In review" if edited else "Klaar om na te kijken",
    "geupload": uploaded,
    "mappings": mappings,
    }