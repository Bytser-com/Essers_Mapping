package be.pxl.services.runtime.domain;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * One entry of {@code /Packages/<customer>/active.json}: which version is active for a package type.
 *
 * <pre>
 * {
 *   "inbound":  { "version": "v3", "updated_at": "2024-10-15T14:30:00Z", "updated_by": "lead_analyst" },
 *   "outbound": { "version": "v1", "updated_at": "2024-10-01T10:00:00Z", "updated_by": "analist_a" }
 * }
 * </pre>
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record ActivePackageInfo(
        @JsonProperty("version") String version,
        @JsonProperty("updated_at") @JsonAlias("updatedAt") String updatedAt,
        @JsonProperty("updated_by") @JsonAlias("updatedBy") String updatedBy
) {
}
