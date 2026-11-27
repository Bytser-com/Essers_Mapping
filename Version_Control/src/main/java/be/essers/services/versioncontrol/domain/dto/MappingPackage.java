package be.essers.services.versioncontrol.domain.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * A mapping package (MPackage.json). Only the {@code meta} block is read here;
 * the {@code mappings} are not needed for the overview and are skipped.
 *
 * <pre>
 * {
 *   "schema_version": "1.0",
 *   "meta": {
 *     "client_name": "nouryon",
 *     "package_version": "1.0.0",
 *     "package_type": "inbound",
 *     "date_created": "2024-06-19T12:00:00Z",
 *     "user_created": "analist_a",
 *     "description": "..."
 *   },
 *   "mappings": [ ... ]
 * }
 * </pre>
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record MappingPackage(
        @JsonProperty("schema_version")
        @JsonAlias("schemaVersion")
        String schemaVersion,

        @JsonProperty("meta")
        @JsonAlias("metadata")
        Meta meta
) {

    /**
     * The {@code meta} block of a mapping package.
     * {@code company} (the SFTP folder) is not part of it, it comes from the directory structure.
     */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Meta(
            @JsonProperty("client_name")
            @JsonAlias({"clientName", "customer", "company"})
            String clientName,

            @JsonProperty("package_version")
            @JsonAlias({"packageVersion", "version"})
            String packageVersion,

            @JsonProperty("package_type")
            @JsonAlias({"packageType", "proposal_type", "type"})
            String packageType,

            @JsonProperty("date_created")
            @JsonAlias({"dateCreated", "created_at", "createdDate"})
            String dateCreated,

            @JsonProperty("user_created")
            @JsonAlias({"userCreated", "created_by", "createdBy"})
            String userCreated,

            @JsonProperty("description")
            String description
    ) {
        public Meta {
            packageType = (packageType != null) ? packageType.toLowerCase() : null;
        }
    }
}
