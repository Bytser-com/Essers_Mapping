package be.essers.services.versioncontrol.domain.proposal.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonPropertyOrder;

import java.util.List;

@JsonPropertyOrder({
        "version",
        "companyname",
        "proposalType",
        "upload_date",
        "upload_time",
        "updated_time",
        "updated_date",
        "createdBy",
        "status",
        "rows"
})
public record ProposalFileDataDto(
        @JsonProperty("version")
        String version,

        @JsonProperty("companyname")
        String companyname,

        @JsonProperty("proposalType")
        String proposalType,

        @JsonProperty("upload_date")
        String uploadDate,

        @JsonProperty("upload_time")
        String uploadTime,

        @JsonProperty("updated_time")
        String updatedTime,

        @JsonProperty("updated_date")
        String updatedDate,

        @JsonProperty("createdBy")
        String createdBy,

        @JsonProperty("status")
        String status,

        @JsonProperty("rows")
        List<ProposalRowDto> rows,

        @JsonProperty("ai_review")
        Object aiReview
) {
    public ProposalFileDataDto {
        proposalType = (proposalType != null) ? proposalType.toLowerCase() : null;
    }

    public ProposalFileDataDto(
            String version,
            String companyName,
            String proposalType,
            String uploadDate,
            String uploadTime,
            String updatedTime,
            String updatedDate,
            String createdBy,
            String status,
            List<ProposalRowDto> rows
    ) {
        this(version, companyName, proposalType, uploadDate, uploadTime, updatedTime, updatedDate, createdBy, status, rows, null);
    }

    public ProposalFileDataDto(
            String version,
            String companyName,
            String uploadDate,
            String uploadTime,
            String updatedTime,
            String updatedDate,
            String createdBy,
            String status,
            List<ProposalRowDto> rows
    ) {
        this(version, companyName, null, uploadDate, uploadTime, updatedTime, updatedDate, createdBy, status, rows, null);
    }

    public ProposalFileDataDto(
            String version,
            String companyName,
            String uploadDate,
            String uploadTime,
            String updatedTime,
            String updatedDate,
            String createdBy,
            List<ProposalRowDto> rows
    ) {
        this(version, companyName, null, uploadDate, uploadTime, updatedTime, updatedDate, createdBy, null, rows, null);
    }
}
