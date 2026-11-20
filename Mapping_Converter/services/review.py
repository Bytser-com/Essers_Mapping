"""AI consistency review of a proposal workbook stored on the shared storage (story 51).

The workbook is read from the proposal folder (same layout as approving):

    <customer>/v<N>/<proposal_type>/MProposal-<Customer>_V<N>.xlsx

and handed to the Gemini review in scripts/pipeline.py, which returns
``{"decision": "ACCEPTED" | "REJECTED", "summary", "findings", "checked_mappings"}``.
"""
from __future__ import annotations

from dataclasses import dataclass

from scripts.pipeline import run_review
from services.proposal_files import find_proposal, find_workbook, read_metadata, validate_reference
from services.storage import Storage


@dataclass(frozen=True)
class ProposalWorkbook:
    path: str        # e.g. "nouryon/v2/inbound/MProposal-Nouryon_V2.xlsx"
    contents: bytes


def load_proposal_workbook(storage: Storage, company: str, version: str, proposal_type: str) -> ProposalWorkbook:
    """Read the Excel workbook of one proposal version.

    Raises ValueError (invalid parameters), ProposalNotFoundError, ProposalConflictError
    (unreadable metadata) or StorageError.
    """
    company, version, proposal_type = validate_reference(company, _with_prefix(version), proposal_type)
    with storage.session() as s:
        location = find_proposal(s, company, version, proposal_type)
        path = find_workbook(s, location, read_metadata(s, location))
        return ProposalWorkbook(path, s.read_bytes(path))


def review_workbook(workbook: ProposalWorkbook) -> dict:
    """Run the Gemini consistency review. Raises InvalidWorkbook or ReviewUnavailable."""
    return run_review(workbook.contents)


def _with_prefix(version: str | None) -> str:
    """Accept both "v2" and "2", as the review endpoint always did."""
    version = (version or '').strip()
    return f'v{version}' if version.isdigit() else version
