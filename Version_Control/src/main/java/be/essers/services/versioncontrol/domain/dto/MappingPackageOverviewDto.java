package be.essers.services.versioncontrol.domain.dto;

/**
 * One row of the mapping package overview: the newest version of one package type of a company.
 * {@code company} is the customer folder on SFTP (used in links),
 * {@code customerName} is {@code meta.client_name} of the package (shown in the list),
 * {@code packageType} is {@code meta.package_type} (or the type folder when it is missing).
 */
public record MappingPackageOverviewDto(
        String company,
        String latestVersion,
        String createdAt,
        String createdBy,
        String customerName,
        String packageType
) {
    public MappingPackageOverviewDto {
        packageType = (packageType != null) ? packageType.toLowerCase() : null;
    }
}
