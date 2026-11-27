package be.pxl.services.runtime.domain;

import tools.jackson.databind.JsonNode;

/**
 * The active mapping package of a customer for one package type, as used by the Java Engine.
 *
 * @param customer       customer folder on {@code sftp-shared} (e.g. "nouryon")
 * @param packageType    package type, e.g. "inbound" or "outbound"
 * @param version        active version (e.g. "v3")
 * @param status         always {@link #STATUS_ACTIVE}: only the active version is returned
 * @param activatedAt    when this version became active, may be null
 * @param activatedBy    who made this version active, may be null
 * @param mappingPackage full content of MPackage.json (meta block and mappings)
 */
public record ActiveMappingPackage(
        String customer,
        String packageType,
        String version,
        String status,
        String activatedAt,
        String activatedBy,
        JsonNode mappingPackage
) {
    public static final String STATUS_ACTIVE = "ACTIVE";
}
