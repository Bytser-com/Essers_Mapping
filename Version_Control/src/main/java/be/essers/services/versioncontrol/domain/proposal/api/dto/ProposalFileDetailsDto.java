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
        String fileContentBase64,
        String proposalType
) {
    public ProposalFileDetailsDto(
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
        this(company, version, filename, fullPath, contentType, sizeBytes, createdDate, createdBy, description, fileContentBase64, null);
    }
}
