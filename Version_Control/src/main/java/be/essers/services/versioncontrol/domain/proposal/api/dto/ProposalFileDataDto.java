package be.essers.services.versioncontrol.domain.proposal.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonPropertyOrder;

import java.util.List;

@JsonPropertyOrder({
        "version",
        "comapnyname",
        "companyname",
        "upload_date",
        "upload_time",
        "updated_time",
        "updated_date",
        "upload_user",
        "status",
        "rows"
})
public record ProposalFileDataDto(
        @JsonProperty("version")
        String version,

        @JsonProperty("comapnyname")
        String comapnyname,

        @JsonProperty("companyname")
        String companyname,

        @JsonProperty("upload_date")
        String uploadDate,

        @JsonProperty("upload_time")
        String uploadTime,

        @JsonProperty("updated_time")
        String updatedTime,

        @JsonProperty("updated_date")
        String updatedDate,

        @JsonProperty("upload_user")
        String uploadUser,

        @JsonProperty("status")
        String status,

        @JsonProperty("rows")
        List<ProposalRowDto> rows
) {
    public ProposalFileDataDto(
            String version,
            String companyName,
            String uploadDate,
            String uploadTime,
            String updatedTime,
            String updatedDate,
            String uploadUser,
            String status,
            List<ProposalRowDto> rows
    ) {
        this(version, companyName, companyName, uploadDate, uploadTime, updatedTime, updatedDate, uploadUser, status, rows);
    }

    // Overload without status for backwards compatibility if needed
    public ProposalFileDataDto(
            String version,
            String companyName,
            String uploadDate,
            String uploadTime,
            String updatedTime,
            String updatedDate,
            String uploadUser,
            List<ProposalRowDto> rows
    ) {
        this(version, companyName, companyName, uploadDate, uploadTime, updatedTime, updatedDate, uploadUser, null, rows);
    }
}
