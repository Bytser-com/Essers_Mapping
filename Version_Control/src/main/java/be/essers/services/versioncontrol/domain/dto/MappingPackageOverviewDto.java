package be.essers.services.versioncontrol.domain.dto;

/**
 * One row of the mapping package overview: the active version of one package type of a company.
 * {@code company} is the customer folder on SFTP (used in links),
 * {@code customerName} is {@code meta.client_name} of the package (shown in the list),
 * {@code packageType} is {@code meta.package_type} (or the type folder when it is missing),
 * {@code activeVersion} is the designated active version (or fallback to latest),
 * {@code activeUpdatedAt} is when the active version was selected,
 * {@code activeUpdatedBy} is who selected the active version.
 */
public record MappingPackageOverviewDto(
        String company,
        String latestVersion,
        String createdAt,
        String createdBy,
        String customerName,
        String packageType,
        String activeVersion,
        String activeUpdatedAt,
        String activeUpdatedBy
) {
    public MappingPackageOverviewDto {
        packageType = (packageType != null) ? packageType.toLowerCase() : null;
        if (activeVersion == null || activeVersion.isBlank()) {
            activeVersion = latestVersion;
        }
    }

    public MappingPackageOverviewDto(
            String company,
            String latestVersion,
            String createdAt,
            String createdBy,
            String customerName,
            String packageType
    ) {
        this(company, latestVersion, createdAt, createdBy, customerName, packageType, latestVersion, createdAt, createdBy);
    }
}
