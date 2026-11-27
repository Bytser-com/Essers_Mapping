package be.essers.services.versioncontrol.service;

import be.essers.services.versioncontrol.domain.dto.ActivePackageInfo;
import be.essers.services.versioncontrol.domain.dto.MappingPackageOverviewDto;
import be.essers.services.versioncontrol.domain.dto.PackageVersionDto;
import be.essers.services.versioncontrol.exception.EntityNotFoundException;
import be.essers.services.versioncontrol.exception.StorageException;
import tools.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.*;

/**
 * Reads and manages mapping packages from SFTP. Layout:
 * {@code <sftp.packages-path>/<companyName>/<version>/<type>/MPackage.json}
 * Active package manifest:
 * {@code <sftp.packages-path>/<companyName>/active.json} (see {@link ActivePackageFile})
 */
@Service
public class SftpPackageStorageService implements PackageStorageService {

    private static final Logger log = LoggerFactory.getLogger(SftpPackageStorageService.class);

    private static final int MAX_COMPANY_LENGTH = 20;

    // Alphabetical on the name shown in the list (customerName, or the company folder), then on the type
    private static final Comparator<MappingPackageOverviewDto> ALPHABETICAL = Comparator
            .comparing((MappingPackageOverviewDto p) -> displayName(p), String.CASE_INSENSITIVE_ORDER)
            .thenComparing(p -> p.packageType() != null ? p.packageType() : "", String.CASE_INSENSITIVE_ORDER);

    private final SftpFolders folders;
    private final ActivePackageFile activePackages;
    private final PackageFolderReader packageReader;
    private final String packagesRoot;

    public SftpPackageStorageService(SftpRemoteFileTemplate template, ObjectMapper objectMapper,
                                     @Value("${sftp.packages-path:/Packages}") String packagesRoot) {
        this.folders = new SftpFolders(template);
        this.activePackages = new ActivePackageFile(template, folders, objectMapper);
        this.packageReader = new PackageFolderReader(template, folders, objectMapper);
        this.packagesRoot = packagesRoot;
    }

    @Override
    public List<MappingPackageOverviewDto> listPackages(String company) {
        try {
            if (company != null && !company.isBlank()) {
                if (company.length() > MAX_COMPANY_LENGTH) {
                    throw new IllegalArgumentException("Company parameter must not exceed " + MAX_COMPANY_LENGTH + " characters");
                }
                String sanitized = SftpFolders.sanitizeSegment(company);
                return getOverviewsForCompany(sanitized);
            } else {
                return listAllPackages();
            }
        } catch (EntityNotFoundException | IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            log.error("Failed to list packages from SFTP share at {}: {}", packagesRoot, e.getMessage(), e);
            throw new StorageException("Unable to read packages from SFTP storage: " + e.getMessage(), e);
        }
    }

    @Override
    public MappingPackageOverviewDto setActivePackage(String company, String packageType, String version, String user) {
        if (company == null || company.isBlank()) {
            throw new IllegalArgumentException("Company parameter must not be empty");
        }
        if (company.length() > MAX_COMPANY_LENGTH) {
            throw new IllegalArgumentException("Company parameter must not exceed " + MAX_COMPANY_LENGTH + " characters");
        }
        if (packageType == null || packageType.isBlank()) {
            throw new IllegalArgumentException("PackageType parameter must not be empty");
        }
        if (version == null || version.isBlank()) {
            throw new IllegalArgumentException("Version parameter must not be empty");
        }

        String resolvedCompany = folders.findSubfolder(packagesRoot, SftpFolders.sanitizeSegment(company));
        if (resolvedCompany == null) {
            throw new EntityNotFoundException("Company directory '" + company + "' does not exist at " + packagesRoot);
        }

        String companyPath = SftpFolders.path(packagesRoot, resolvedCompany);
        String sanitizedType = SftpFolders.sanitizeSegment(packageType).toLowerCase();
        String sanitizedVersion = SftpFolders.sanitizeSegment(version);

        // Verify that the requested version directory exists for this company
        String resolvedVersion = folders.findSubfolder(companyPath, sanitizedVersion);
        if (resolvedVersion == null) {
            throw new EntityNotFoundException("Version directory '" + sanitizedVersion + "' does not exist for company '" + resolvedCompany + "'");
        }

        String versionPath = SftpFolders.path(companyPath, resolvedVersion);
        String resolvedType = folders.findSubfolder(versionPath, sanitizedType);
        if (resolvedType == null) {
            throw new EntityNotFoundException("Package type '" + sanitizedType + "' does not exist in version '" + resolvedVersion + "' for company '" + resolvedCompany + "'");
        }

        PackageFolder pkg = packageReader.read(versionPath, resolvedType);
        String problem = pkg.problem();
        if (problem != null) {
            throw new EntityNotFoundException(
                    "Package at " + SftpFolders.path(versionPath, resolvedType) + " is invalid: " + problem);
        }

        Map<String, ActivePackageInfo> activeMap = activePackages.read(companyPath);
        String nowIso = Instant.now().toString();
        String effectiveUser = (user != null && !user.isBlank()) ? user.trim() : "analist";
        activeMap.put(sanitizedType, new ActivePackageInfo(resolvedVersion, nowIso, effectiveUser));

        activePackages.write(companyPath, activeMap);
        log.info("Updated active package for {}/{}: version={}, user={}", resolvedCompany, sanitizedType, resolvedVersion, effectiveUser);

        // Return updated overview directly
        return new MappingPackageOverviewDto(
                resolvedCompany,
                resolvedVersion,
                pkg.createdAt(),
                pkg.createdBy(),
                pkg.customerName(),
                sanitizedType,
                resolvedVersion,
                nowIso,
                effectiveUser
        );
    }

    @Override
    public List<PackageVersionDto> listVersions(String company, String packageType) {
        if (company == null || company.isBlank()) {
            throw new IllegalArgumentException("Company parameter must not be empty");
        }
        if (packageType == null || packageType.isBlank()) {
            throw new IllegalArgumentException("PackageType parameter must not be empty");
        }

        String resolvedCompany = folders.findSubfolder(packagesRoot, SftpFolders.sanitizeSegment(company));
        if (resolvedCompany == null) {
            throw new EntityNotFoundException("Company directory '" + company + "' does not exist at " + packagesRoot);
        }

        String companyPath = SftpFolders.path(packagesRoot, resolvedCompany);
        String sanitizedType = SftpFolders.sanitizeSegment(packageType).toLowerCase();
        Map<String, ActivePackageInfo> activeMap = activePackages.read(companyPath);
        ActivePackageInfo activeInfo = activeMap.get(sanitizedType);

        List<String> versions = folders.subfolders(companyPath);
        versions.sort(VersionComparator.INSTANCE);

        List<PackageVersionDto> result = new ArrayList<>();
        // Walk from newest to oldest
        for (int i = versions.size() - 1; i >= 0; i--) {
            String version = versions.get(i);
            String versionPath = SftpFolders.path(companyPath, version);

            for (String typeName : folders.subfolders(versionPath)) {
                if (sanitizedType.equalsIgnoreCase(typeName)) {
                    PackageFolder pkg = packageReader.read(versionPath, typeName);
                    if (!pkg.isValid()) {
                        continue;
                    }

                    boolean isActive = (activeInfo != null && activeInfo.version() != null)
                            ? version.equalsIgnoreCase(activeInfo.version())
                            : (i == versions.size() - 1); // default newest is active if no active.json

                    result.add(new PackageVersionDto(version, isActive, pkg.createdAt(), pkg.createdBy(),
                            pkg.description()));
                }
            }
        }
        return result;
    }

    private List<MappingPackageOverviewDto> getOverviewsForCompany(String company) {
        String resolvedCompany = folders.findSubfolder(packagesRoot, company);
        if (resolvedCompany == null) {
            throw new EntityNotFoundException("Company directory '" + company + "' does not exist at " + packagesRoot);
        }

        String companyPath = SftpFolders.path(packagesRoot, resolvedCompany);
        List<String> versions = folders.subfolders(companyPath);
        versions.sort(VersionComparator.INSTANCE);
        if (versions.isEmpty()) {
            throw new EntityNotFoundException("No package versions found for company '" + resolvedCompany + "'");
        }

        List<MappingPackageOverviewDto> overviews = findLatestPackagesForCompany(resolvedCompany, versions);
        overviews.sort(ALPHABETICAL);
        if (overviews.isEmpty()) {
            String latestVersion = versions.get(versions.size() - 1);
            MappingPackageOverviewDto fallback = buildCompanyOverviewFallback(resolvedCompany, latestVersion);
            if (fallback != null) {
                return List.of(fallback);
            }
            throw new EntityNotFoundException("No packages found for company '" + resolvedCompany + "'");
        }
        return overviews;
    }

    private List<MappingPackageOverviewDto> listAllPackages() {
        if (!folders.exists(packagesRoot)) {
            log.warn("Root packages directory '{}' does not exist on SFTP server", packagesRoot);
            return Collections.emptyList();
        }

        List<MappingPackageOverviewDto> results = new ArrayList<>();
        for (String companyName : folders.subfolders(packagesRoot)) {
            List<String> versions = folders.subfolders(SftpFolders.path(packagesRoot, companyName));
            versions.sort(VersionComparator.INSTANCE);
            results.addAll(findLatestPackagesForCompany(companyName, versions));
        }

        results.sort(ALPHABETICAL);
        return results;
    }

    /**
     * Walks the versions and active.json for a company and returns one overview per package type.
     * The active version is retrieved from {@code active.json} if present, otherwise falling back
     * to the latest version found.
     */
    private List<MappingPackageOverviewDto> findLatestPackagesForCompany(String companyName, List<String> versions) {
        String companyPath = SftpFolders.path(packagesRoot, companyName);
        Map<String, ActivePackageInfo> activeMap = activePackages.read(companyPath);

        // Group packages by type: packageType -> (version -> package folder)
        Map<String, String> latestVersionByType = new LinkedHashMap<>();
        Map<String, Map<String, PackageFolder>> versionsByType = new LinkedHashMap<>();

        for (int i = versions.size() - 1; i >= 0; i--) {
            String version = versions.get(i);
            String versionPath = SftpFolders.path(companyPath, version);

            for (String typeName : folders.subfolders(versionPath)) {
                PackageFolder pkg = packageReader.read(versionPath, typeName);
                String problem = pkg.problem();
                if (problem != null) {
                    log.warn("Skipping package {}: {}", SftpFolders.path(versionPath, typeName), problem);
                    continue;
                }
                String packageType = pkg.packageType();
                latestVersionByType.putIfAbsent(packageType, version);
                versionsByType.computeIfAbsent(packageType, k -> new LinkedHashMap<>()).put(version, pkg);
            }
        }

        List<MappingPackageOverviewDto> result = new ArrayList<>();
        for (Map.Entry<String, String> entry : latestVersionByType.entrySet()) {
            String packageType = entry.getKey();
            String latestVer = entry.getValue();
            ActivePackageInfo activeInfo = activeMap.get(packageType);

            String activeVer = (activeInfo != null && activeInfo.version() != null)
                    ? activeInfo.version()
                    : latestVer;

            Map<String, PackageFolder> typeVersions = versionsByType.get(packageType);
            PackageFolder activeData = (typeVersions != null) ? typeVersions.get(activeVer) : null;
            if (activeData == null && typeVersions != null) {
                // If active version in active.json points to a version not found, fallback to latest
                activeData = typeVersions.get(latestVer);
                activeVer = latestVer;
            }

            String activeUpdatedAt = (activeInfo != null && activeInfo.updatedAt() != null)
                    ? activeInfo.updatedAt()
                    : (activeData != null ? activeData.createdAt() : null);

            String activeUpdatedBy = (activeInfo != null && activeInfo.updatedBy() != null)
                    ? activeInfo.updatedBy()
                    : (activeData != null ? activeData.createdBy() : null);

            String customerName = activeData != null ? activeData.customerName() : null;
            String createdAt = activeData != null ? activeData.createdAt() : null;
            String createdBy = activeData != null ? activeData.createdBy() : null;

            result.add(new MappingPackageOverviewDto(
                    companyName,
                    activeVer,
                    createdAt,
                    createdBy,
                    customerName,
                    packageType,
                    activeVer,
                    activeUpdatedAt,
                    activeUpdatedBy
            ));
        }

        return result;
    }

    // First type folder of the latest version, even when its MPackage.json is missing or invalid
    private MappingPackageOverviewDto buildCompanyOverviewFallback(String companyName, String version) {
        String versionPath = SftpFolders.path(packagesRoot, companyName, version);
        List<String> types = folders.subfolders(versionPath);
        if (types.isEmpty()) {
            return null;
        }
        PackageFolder pkg = packageReader.read(versionPath, types.get(0));
        return new MappingPackageOverviewDto(
                companyName,
                version,
                pkg.createdAt(),
                pkg.createdBy(),
                pkg.customerName(),
                pkg.packageType(),
                version,
                pkg.createdAt(),
                pkg.createdBy()
        );
    }

    private static String displayName(MappingPackageOverviewDto p) {
        return (p.customerName() != null && !p.customerName().isBlank()) ? p.customerName() : p.company();
    }
}
