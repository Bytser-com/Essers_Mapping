package be.essers.services.versioncontrol.domain.dto;

/**
 * Details of one version of a package type of a company.
 */
public record PackageVersionDto(
        String version,
        boolean isActive,
        String createdAt,
        String createdBy,
        String description
) {
}
