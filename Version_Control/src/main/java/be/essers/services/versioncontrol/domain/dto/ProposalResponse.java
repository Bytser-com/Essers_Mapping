package be.essers.services.versioncontrol.domain.dto;

import be.essers.services.versioncontrol.domain.Proposal;
import be.essers.services.versioncontrol.domain.ProposalStatus;

import java.time.Instant;
import java.util.UUID;

public record ProposalResponse(
        UUID id,
        String title,
        String description,
        ProposalStatus status,
        Instant createdAt,
        Instant updatedAt
) {
    public static ProposalResponse from(Proposal proposal) {
        return new ProposalResponse(
                proposal.getId(),
                proposal.getTitle(),
                proposal.getDescription(),
                proposal.getStatus(),
                proposal.getCreatedAt(),
                proposal.getUpdatedAt()
        );
    }
}
