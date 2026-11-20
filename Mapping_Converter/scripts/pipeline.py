"""Coordinate the Excel-only review without deciding business mapping rules."""

from __future__ import annotations

from .excel_review import read_mapping_proposal
from .gemini_review import review_with_gemini


def run_review(contents: bytes) -> dict:
    """Extract the submitted Excel rows and return Gemini's review decision."""
    records = read_mapping_proposal(contents)
    return review_with_gemini(records)
