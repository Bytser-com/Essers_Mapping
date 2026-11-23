package be.essers.services.versioncontrol.domain.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonIgnoreProperties(ignoreUnknown = true)
public record SetActivePackageRequest(
        @JsonProperty("company") String company,
        @JsonProperty("packageType") String packageType,
        @JsonProperty("version") String version,
        @JsonProperty("user") String user
) {
}
