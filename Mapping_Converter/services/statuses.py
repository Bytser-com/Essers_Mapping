"""Workflow statuses of a mapping proposal, shared by all converter services.

Same codes as Mapping_Proposal (services/proposals.py) writes in proposal.json; the
frontend translates them to Dutch labels.
"""
from __future__ import annotations

from enum import StrEnum


class ProposalStatus(StrEnum):
    AI_GENERATING = 'AI_GENERATING'            # "AI maakt voorstel"
    READY_FOR_REVIEW = 'READY_FOR_REVIEW'      # "Klaar om na te kijken"
    IN_REVIEW = 'IN_REVIEW'                    # "In review"
    AI_CHECKING_REVIEW = 'AI_CHECKING_REVIEW'  # "AI-controle bezig"
    RETURNED = 'RETURNED'                      # "Teruggestuurd"


# Version_Control writes this spelling after a reviewed Excel was uploaded again.
LEGACY_IN_REVIEW = 'In review'

# Statuses in which an analyst may approve a proposal.
APPROVABLE_STATUSES = frozenset({ProposalStatus.READY_FOR_REVIEW, ProposalStatus.IN_REVIEW, LEGACY_IN_REVIEW})
