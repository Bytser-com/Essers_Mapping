package be.essers.services.versioncontrol.domain.proposal.api.dto;

public record CompanyProposalOverviewDto(
        String company,
        String latestVersion,
        String filename,
        String fullPath,
        String createdDate,
        String createdBy,
        String description
) {
}
