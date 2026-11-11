package be.essers.services.versioncontrol.domain.proposal.api.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record ProposalMetadata(
        String company,
        String version,
        String filename,
        String createdDate,
        String createdBy,
        String description
) {
}
