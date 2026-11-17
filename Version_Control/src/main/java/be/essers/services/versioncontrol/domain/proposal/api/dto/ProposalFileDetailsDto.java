package be.essers.services.versioncontrol.domain.proposal.api.dto;

public record ProposalFileDetailsDto(
        String company,
        String version,
        String filename,
        String fullPath,
        String contentType,
        long sizeBytes,
        String createdDate,
        String createdBy,
        String description,
        String fileContentBase64
) {
}
