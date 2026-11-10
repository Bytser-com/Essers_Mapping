package be.essers.services.versioncontrol.domain.proposal.api.dto;

public record ProposalFileDto(
        String company,
        String filename,
        String fullPath
) {
}
