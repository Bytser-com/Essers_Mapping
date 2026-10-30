"""Routes for the proposals overview on the Home page (GET /proposals)."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from scripts.config import proposals_dir
from services.proposals import AiStatus, ProposalStatus, ProposalStore

router = APIRouter(prefix='/proposals', tags=['proposals'])


# ---------------------------------------------------------------------------
# Response models: they define the JSON the frontend receives and appear in /docs.
# ---------------------------------------------------------------------------
class ProposalOut(BaseModel):
    id: str                          # "<customer folder>/v<version>", use it to open a proposal later
    customer: str                    # column KLANT
    version: int                     # column VERSIE (show as "v1")
    uploaded_at: datetime            # column GEÜPLOAD OP (ISO 8601 with timezone)
    status: ProposalStatus           # column STATUS (code; the frontend shows the Dutch label)
    ai_status: Optional[AiStatus] = None  # column AI-STATUS; null = "—"
    can_open: bool                   # whether the "Openen" button is enabled


class ProposalListOut(BaseModel):
    total: int                       # number shown in the "Proposals" badge
    proposals: List[ProposalOut]


# Dependency: tests replace this with a store on a temporary folder.
def get_proposal_store() -> ProposalStore:
    return ProposalStore(proposals_dir())


@router.get('', response_model=ProposalListOut)
def list_proposals(
    all_versions: bool = Query(False, description='Return every version instead of only the latest per customer.'),
    store: ProposalStore = Depends(get_proposal_store),
) -> ProposalListOut:
    """Proposals on the shared storage, newest upload first (the Home overview)."""
    proposals = store.list_proposals(all_versions=all_versions)
    return ProposalListOut(
        total=len(proposals),
        proposals=[ProposalOut(**proposal.to_dict()) for proposal in proposals],
    )
