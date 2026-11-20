package be.essers.services.versioncontrol.domain.dto;

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

        @JsonAlias({"description", "error"})
        String description,

        @JsonAlias({"status", "proposal_status", "proposalStatus"})
        String status,

        @JsonAlias({"ai_status", "aiStatus"})
        String aiStatus,

        @JsonAlias({"updated_at", "updatedAt", "updated_date", "updatedDate"})
        String updatedAt,

        @JsonAlias({"proposal_type", "proposalType"})
        String proposalType,

        @JsonAlias({"ai_review", "aiReview"})
        Object aiReview
) {
    public ProposalMetadata {
        proposalType = (proposalType != null) ? proposalType.toLowerCase() : null;
    }

    public ProposalMetadata(
            String company,
            String version,
            String filename,
            String createdDate,
            String createdBy,
            String description,
            String status,
            String aiStatus,
            String updatedAt,
            String proposalType
    ) {
        this(company, version, filename, createdDate, createdBy, description, status, aiStatus, updatedAt, proposalType, null);
    }

    public ProposalMetadata(
            String company,
            String version,
            String filename,
            String createdDate,
            String createdBy,
            String description,
            String status,
            String aiStatus,
            String updatedAt
    ) {
        this(company, version, filename, createdDate, createdBy, description, status, aiStatus, updatedAt, null, null);
    }

    public ProposalMetadata(
            String company,
            String version,
            String filename,
            String createdDate,
            String createdBy,
            String description,
            String status,
            String aiStatus
    ) {
        this(company, version, filename, createdDate, createdBy, description, status, aiStatus, null, null, null);
    }
}
