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
    private static final String DEFAULT_USER = "analist";

    // Alphabetical on the name shown in the list (customerName, or the company folder), then on the type
    private static final Comparator<MappingPackageOverviewDto> ALPHABETICAL = Comparator
            .comparing(SftpPackageStorageService::displayName, String.CASE_INSENSITIVE_ORDER)
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
            if (company == null || company.isBlank()) {
                return listAllPackages();
            }
            requireMaxLength(company);
            return listPackagesOfCompany(company);
        } catch (EntityNotFoundException | IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            log.error("Failed to list packages from SFTP share at {}: {}", packagesRoot, e.getMessage(), e);
            throw new StorageException("Unable to read packages from SFTP storage: " + e.getMessage(), e);
        }
    }

    @Override
    public MappingPackageOverviewDto setActivePackage(String company, String packageType, String version, String user) {
        requireText(company, "Company");
        requireMaxLength(company);
        requireText(packageType, "PackageType");
        requireText(version, "Version");

        String resolvedCompany = findCompanyFolder(company);
        String companyPath = SftpFolders.path(packagesRoot, resolvedCompany);
        String type = SftpFolders.sanitizeSegment(packageType).toLowerCase();
        String requestedVersion = SftpFolders.sanitizeSegment(version);

        String resolvedVersion = requireSubfolder(companyPath, requestedVersion,
                "Version directory '" + requestedVersion + "' does not exist for company '" + resolvedCompany + "'");
        String versionPath = SftpFolders.path(companyPath, resolvedVersion);
        String resolvedType = requireSubfolder(versionPath, type,
                "Package type '" + type + "' does not exist in version '" + resolvedVersion
                        + "' for company '" + resolvedCompany + "'");
        PackageFolder pkg = requireValidPackage(versionPath, resolvedType);

        String updatedAt = Instant.now().toString();
        String updatedBy = userOrDefault(user);
        Map<String, ActivePackageInfo> activeByType = activePackages.read(companyPath);
        activeByType.put(type, new ActivePackageInfo(resolvedVersion, updatedAt, updatedBy));
        activePackages.write(companyPath, activeByType);
        log.info("Updated active package for {}/{}: version={}, user={}",
                resolvedCompany, type, resolvedVersion, updatedBy);

        return new MappingPackageOverviewDto(resolvedCompany, resolvedVersion, pkg.createdAt(), pkg.createdBy(),
                pkg.customerName(), type, resolvedVersion, updatedAt, updatedBy);
    }

    @Override
    public List<PackageVersionDto> listVersions(String company, String packageType) {
        requireText(company, "Company");
        requireText(packageType, "PackageType");

        String companyPath = SftpFolders.path(packagesRoot, findCompanyFolder(company));
        String type = SftpFolders.sanitizeSegment(packageType).toLowerCase();
        ActivePackageInfo activeInfo = activePackages.read(companyPath).get(type);
        List<String> versions = sortedVersions(companyPath);
        String newestVersion = versions.isEmpty() ? null : versions.get(versions.size() - 1);

        List<PackageVersionDto> result = new ArrayList<>();
        for (String version : newestFirst(versions)) {
            boolean active = isActiveVersion(version, activeInfo, newestVersion);
            for (PackageFolder pkg : validPackagesOfType(SftpFolders.path(companyPath, version), type)) {
                result.add(new PackageVersionDto(version, active, pkg.createdAt(), pkg.createdBy(), pkg.description()));
            }
        }
        return result;
    }

    // --- Overview -------------------------------------------------------------------------

    private List<MappingPackageOverviewDto> listAllPackages() {
        if (!folders.exists(packagesRoot)) {
            log.warn("Root packages directory '{}' does not exist on SFTP server", packagesRoot);
            return Collections.emptyList();
        }
        List<MappingPackageOverviewDto> results = new ArrayList<>();
        for (String companyName : folders.subfolders(packagesRoot)) {
            List<String> versions = sortedVersions(SftpFolders.path(packagesRoot, companyName));
            results.addAll(overviewsOfCompany(companyName, versions));
        }
        results.sort(ALPHABETICAL);
        return results;
    }

    private List<MappingPackageOverviewDto> listPackagesOfCompany(String company) {
        String resolvedCompany = findCompanyFolder(company);
        List<String> versions = sortedVersions(SftpFolders.path(packagesRoot, resolvedCompany));
        if (versions.isEmpty()) {
            throw new EntityNotFoundException("No package versions found for company '" + resolvedCompany + "'");
        }

        List<MappingPackageOverviewDto> overviews = overviewsOfCompany(resolvedCompany, versions);
        if (!overviews.isEmpty()) {
            overviews.sort(ALPHABETICAL);
            return overviews;
        }
        MappingPackageOverviewDto fallback = fallbackOverview(resolvedCompany, versions.get(versions.size() - 1));
        if (fallback == null) {
            throw new EntityNotFoundException("No packages found for company '" + resolvedCompany + "'");
        }
        return List.of(fallback);
    }

    /**
     * One overview per package type of a company. The active version comes from {@code active.json};
     * without an entry there, or when it points to a version that does not exist, the newest version is used.
     */
    private List<MappingPackageOverviewDto> overviewsOfCompany(String companyName, List<String> versions) {
        String companyPath = SftpFolders.path(packagesRoot, companyName);
        Map<String, ActivePackageInfo> activeByType = activePackages.read(companyPath);

        List<MappingPackageOverviewDto> result = new ArrayList<>();
        validPackagesByType(companyPath, versions).forEach((type, packagesByVersion) ->
                result.add(overviewOfType(companyName, type, packagesByVersion, activeByType.get(type))));
        return result;
    }

    // packageType -> (version -> package), versions newest first
    private Map<String, Map<String, PackageFolder>> validPackagesByType(String companyPath, List<String> versions) {
        Map<String, Map<String, PackageFolder>> byType = new LinkedHashMap<>();
        for (String version : newestFirst(versions)) {
            String versionPath = SftpFolders.path(companyPath, version);
            for (String typeName : folders.subfolders(versionPath)) {
                PackageFolder pkg = packageReader.read(versionPath, typeName);
                if (pkg.isValid()) {
                    byType.computeIfAbsent(pkg.packageType(), k -> new LinkedHashMap<>()).put(version, pkg);
                } else {
                    logSkipped(versionPath, pkg);
                }
            }
        }
        return byType;
    }

    private static void logSkipped(String versionPath, PackageFolder pkg) {
        if (log.isWarnEnabled()) {
            log.warn("Skipping package {}: {}", SftpFolders.path(versionPath, pkg.typeName()), pkg.problem());
        }
    }

    private static MappingPackageOverviewDto overviewOfType(String companyName, String type,
                                                            Map<String, PackageFolder> packagesByVersion,
                                                            ActivePackageInfo activeInfo) {
        String newestVersion = packagesByVersion.keySet().iterator().next();
        boolean activeExists = activeInfo != null && packagesByVersion.containsKey(activeInfo.version());
        String activeVersion = activeExists ? activeInfo.version() : newestVersion;
        PackageFolder pkg = packagesByVersion.get(activeVersion);

        boolean hasUpdatedAt = activeInfo != null && activeInfo.updatedAt() != null;
        boolean hasUpdatedBy = activeInfo != null && activeInfo.updatedBy() != null;
        String updatedAt = hasUpdatedAt ? activeInfo.updatedAt() : pkg.createdAt();
        String updatedBy = hasUpdatedBy ? activeInfo.updatedBy() : pkg.createdBy();
        return new MappingPackageOverviewDto(companyName, activeVersion, pkg.createdAt(), pkg.createdBy(),
                pkg.customerName(), type, activeVersion, updatedAt, updatedBy);
    }

    // First type folder of the latest version, even when its MPackage.json is missing or invalid
    private MappingPackageOverviewDto fallbackOverview(String companyName, String version) {
        String versionPath = SftpFolders.path(packagesRoot, companyName, version);
        List<String> types = folders.subfolders(versionPath);
        if (types.isEmpty()) {
            return null;
        }
        PackageFolder pkg = packageReader.read(versionPath, types.get(0));
        return new MappingPackageOverviewDto(companyName, version, pkg.createdAt(), pkg.createdBy(),
                pkg.customerName(), pkg.packageType(), version, pkg.createdAt(), pkg.createdBy());
    }

    // --- Versions -------------------------------------------------------------------------

    private List<PackageFolder> validPackagesOfType(String versionPath, String type) {
        List<PackageFolder> packages = new ArrayList<>();
        for (String typeName : folders.subfolders(versionPath)) {
            if (type.equalsIgnoreCase(typeName)) {
                PackageFolder pkg = packageReader.read(versionPath, typeName);
                if (pkg.isValid()) {
                    packages.add(pkg);
                }
            }
        }
        return packages;
    }

    // Without an entry in active.json the newest version is the active one
    private static boolean isActiveVersion(String version, ActivePackageInfo activeInfo, String newestVersion) {
        if (activeInfo != null && activeInfo.version() != null) {
            return version.equalsIgnoreCase(activeInfo.version());
        }
        return version.equals(newestVersion);
    }

    // --- Folders and parameters ---------------------------------------------------------

    private List<String> sortedVersions(String companyPath) {
        List<String> versions = folders.subfolders(companyPath);
        versions.sort(VersionComparator.INSTANCE);
        return versions;
    }

    private static List<String> newestFirst(List<String> sortedVersions) {
        List<String> reversed = new ArrayList<>(sortedVersions);
        Collections.reverse(reversed);
        return reversed;
    }

    private String findCompanyFolder(String company) {
        return requireSubfolder(packagesRoot, SftpFolders.sanitizeSegment(company),
                "Company directory '" + company + "' does not exist at " + packagesRoot);
    }

    private String requireSubfolder(String parentPath, String name, String notFoundMessage) {
        String folder = folders.findSubfolder(parentPath, name);
        if (folder == null) {
            throw new EntityNotFoundException(notFoundMessage);
        }
        return folder;
    }

    private PackageFolder requireValidPackage(String versionPath, String typeName) {
        PackageFolder pkg = packageReader.read(versionPath, typeName);
        if (!pkg.isValid()) {
            throw new EntityNotFoundException(
                    "Package at " + SftpFolders.path(versionPath, typeName) + " is invalid: " + pkg.problem());
        }
        return pkg;
    }

    private static void requireText(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " parameter must not be empty");
        }
    }

    private static void requireMaxLength(String company) {
        if (company.length() > MAX_COMPANY_LENGTH) {
            throw new IllegalArgumentException(
                    "Company parameter must not exceed " + MAX_COMPANY_LENGTH + " characters");
        }
    }

    private static String userOrDefault(String user) {
        return user != null && !user.isBlank() ? user.trim() : DEFAULT_USER;
    }

    private static String displayName(MappingPackageOverviewDto p) {
        return p.customerName() != null && !p.customerName().isBlank() ? p.customerName() : p.company();
    }
}
