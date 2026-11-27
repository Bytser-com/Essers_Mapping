package be.pxl.services.runtime.domain;

import tools.jackson.databind.JsonNode;

/**
 * The active mapping package of a customer for one package type, with the full MPackage.json.
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
