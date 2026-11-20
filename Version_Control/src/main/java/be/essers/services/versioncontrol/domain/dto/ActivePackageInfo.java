package be.essers.services.versioncontrol.domain.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Metadata stored in {@code /Packages/<company>/active.json} per package type.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record ActivePackageInfo(
        @JsonProperty("version")
        String version,

        @JsonProperty("updated_at")
        @JsonAlias("updatedAt")
        String updatedAt,

        @JsonProperty("updated_by")
        @JsonAlias("updatedBy")
        String updatedBy
) {
}
