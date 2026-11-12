package be.essers.services.versioncontrol.domain.proposal.api.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record ProposalMetadata(
        @JsonAlias({"company", "customer"})
        String company,

        String version,

        String filename,

        @JsonAlias({"createdDate", "uploaded_at", "created_date", "uploadedAt"})
        String createdDate,

        @JsonAlias({"createdBy", "created_by", "creator"})
        String createdBy,

        String description,

        @JsonAlias({"status", "proposal_status", "proposalStatus"})
        String status,

        @JsonAlias({"ai_status", "aiStatus"})
        String aiStatus
) {
}
