package be.essers.services.versioncontrol.service;

import be.essers.services.versioncontrol.domain.dto.ActivePackageInfo;
import be.essers.services.versioncontrol.domain.dto.MappingPackageOverviewDto;
import be.essers.services.versioncontrol.domain.dto.MappingPackage;
import be.essers.services.versioncontrol.domain.dto.PackageVersionDto;
import be.essers.services.versioncontrol.exception.EntityNotFoundException;
import be.essers.services.versioncontrol.exception.StorageException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import org.apache.sshd.sftp.client.SftpClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;
import org.springframework.stereotype.Service;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.file.attribute.FileTime;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeParseException;
import java.util.*;

/**
 * Reads and manages mapping packages from SFTP. Layout:
 * {@code <sftp.packages-path>/<companyName>/<version>/<type>/MPackage.json}
 * Active package manifest:
 * {@code <sftp.packages-path>/<companyName>/active.json}
 */
@Service
public class SftpPackageStorageService implements PackageStorageService {

    private static final Logger log = LoggerFactory.getLogger(SftpPackageStorageService.class);

    private static final String METADATA_FILENAME = "MPackage.json";
    private static final String ACTIVE_FILENAME = "active.json";
    private static final int MAX_COMPANY_LENGTH = 20;

    // Alphabetical on the name shown in the list (customerName, or the company folder), then on the type
    private static final Comparator<MappingPackageOverviewDto> ALPHABETICAL = Comparator
            .comparing((MappingPackageOverviewDto p) -> displayName(p), String.CASE_INSENSITIVE_ORDER)
            .thenComparing(p -> p.packageType() != null ? p.packageType() : "", String.CASE_INSENSITIVE_ORDER);

    private final SftpRemoteFileTemplate template;
    private final SftpFolders folders;
    private final String packagesRoot;
    private final ObjectMapper objectMapper;

    public SftpPackageStorageService(SftpRemoteFileTemplate template, ObjectMapper objectMapper,
                                     @Value("${sftp.packages-path:/Packages}") String packagesRoot) {
        this.template = template;
        this.folders = new SftpFolders(template);
        this.packagesRoot = packagesRoot;
        this.objectMapper = objectMapper;
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

        String typePath = SftpFolders.path(versionPath, resolvedType);
        SftpClient.DirEntry[] typeEntries = folders.list(typePath);
        MappingPackage.Meta metadata = readMetadata(typePath, typeEntries);
        String problem = findMetadataProblem(metadata);
        if (problem != null) {
            throw new EntityNotFoundException("Package at " + typePath + " is invalid: " + problem);
        }

        // Read current active.json or start empty
        Map<String, ActivePackageInfo> activeMap = readActivePackages(companyPath);
        String nowIso = Instant.now().toString();
        String effectiveUser = (user != null && !user.isBlank()) ? user.trim() : "analist";
        activeMap.put(sanitizedType, new ActivePackageInfo(resolvedVersion, nowIso, effectiveUser));

        // Write active.json atomically
        String activeJsonPath = SftpFolders.path(companyPath, ACTIVE_FILENAME);
        String tempPath = SftpFolders.path(companyPath, "." + ACTIVE_FILENAME + ".tmp");
        try {
            byte[] bytes = objectMapper.writerWithDefaultPrettyPrinter().writeValueAsBytes(activeMap);
            template.execute(session -> {
                session.write(new ByteArrayInputStream(bytes), tempPath);
                try {
                    session.rename(tempPath, activeJsonPath);
                } catch (Exception e) {
                    try {
                        session.remove(activeJsonPath);
                    } catch (Exception ignored) {
                    }
                    session.rename(tempPath, activeJsonPath);
                }
                return null;
            });
            log.info("Updated active package for {}/{}: version={}, user={}", resolvedCompany, sanitizedType, resolvedVersion, effectiveUser);
        } catch (Exception e) {
            log.error("Failed to write active.json at {}: {}", activeJsonPath, e.getMessage(), e);
            throw new StorageException("Unable to update active.json: " + e.getMessage(), e);
        }

        // Return updated overview directly
        String createdAt = extractCreatedAt(typeEntries, metadata);
        String createdBy = metadata != null ? metadata.userCreated() : null;
        String customerName = metadata != null ? metadata.clientName() : null;

        return new MappingPackageOverviewDto(
                resolvedCompany,
                resolvedVersion,
                createdAt,
                createdBy,
                customerName,
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
        Map<String, ActivePackageInfo> activeMap = readActivePackages(companyPath);
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
                    String typePath = SftpFolders.path(versionPath, typeName);
                    SftpClient.DirEntry[] typeEntries = folders.list(typePath);
                    MappingPackage.Meta metadata = readMetadata(typePath, typeEntries);
                    String problem = findMetadataProblem(metadata);
                    if (problem != null) {
                        continue;
                    }

                    boolean isActive = (activeInfo != null && activeInfo.version() != null)
                            ? version.equalsIgnoreCase(activeInfo.version())
                            : (i == versions.size() - 1); // default newest is active if no active.json

                    String createdAt = extractCreatedAt(typeEntries, metadata);
                    String createdBy = metadata != null ? metadata.userCreated() : null;
                    String description = metadata != null ? metadata.description() : null;

                    result.add(new PackageVersionDto(version, isActive, createdAt, createdBy, description));
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

    private record VersionPackageData(String version, SftpClient.DirEntry[] entries, MappingPackage.Meta metadata) {}

    /**
     * Walks the versions and active.json for a company and returns one overview per package type.
     * The active version is retrieved from {@code active.json} if present, otherwise falling back
     * to the latest version found.
     */
    private List<MappingPackageOverviewDto> findLatestPackagesForCompany(String companyName, List<String> versions) {
        String companyPath = SftpFolders.path(packagesRoot, companyName);
        Map<String, ActivePackageInfo> activeMap = readActivePackages(companyPath);

        // Group packages by type: packageType -> (version -> VersionPackageData)
        Map<String, String> latestVersionByType = new LinkedHashMap<>();
        Map<String, Map<String, VersionPackageData>> versionsByType = new LinkedHashMap<>();

        for (int i = versions.size() - 1; i >= 0; i--) {
            String version = versions.get(i);
            String versionPath = SftpFolders.path(companyPath, version);

            for (String typeName : folders.subfolders(versionPath)) {
                String typePath = SftpFolders.path(versionPath, typeName);
                SftpClient.DirEntry[] typeEntries = folders.list(typePath);
                MappingPackage.Meta metadata = readMetadata(typePath, typeEntries);
                String problem = findMetadataProblem(metadata);
                if (problem != null) {
                    log.warn("Skipping package {}: {}", typePath, problem);
                    continue;
                }
                String packageType = resolvePackageType(metadata, typeName);
                latestVersionByType.putIfAbsent(packageType, version);
                versionsByType.computeIfAbsent(packageType, k -> new LinkedHashMap<>())
                        .put(version, new VersionPackageData(version, typeEntries, metadata));
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

            Map<String, VersionPackageData> typeVersions = versionsByType.get(packageType);
            VersionPackageData activeData = (typeVersions != null) ? typeVersions.get(activeVer) : null;
            if (activeData == null && typeVersions != null) {
                // If active version in active.json points to a version not found, fallback to latest
                activeData = typeVersions.get(latestVer);
                activeVer = latestVer;
            }

            String activeUpdatedAt = (activeInfo != null && activeInfo.updatedAt() != null)
                    ? activeInfo.updatedAt()
                    : (activeData != null ? extractCreatedAt(activeData.entries(), activeData.metadata()) : null);

            String activeUpdatedBy = (activeInfo != null && activeInfo.updatedBy() != null)
                    ? activeInfo.updatedBy()
                    : (activeData != null && activeData.metadata() != null ? activeData.metadata().userCreated() : null);

            String customerName = activeData != null && activeData.metadata() != null
                    ? activeData.metadata().clientName()
                    : null;

            String createdAt = activeData != null
                    ? extractCreatedAt(activeData.entries(), activeData.metadata())
                    : null;

            String createdBy = activeData != null && activeData.metadata() != null
                    ? activeData.metadata().userCreated()
                    : null;

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

    private Map<String, ActivePackageInfo> readActivePackages(String companyPath) {
        String activePath = SftpFolders.path(companyPath, ACTIVE_FILENAME);
        if (!folders.exists(activePath)) {
            return new HashMap<>();
        }
        try {
            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            boolean success = template.get(activePath, in -> in.transferTo(baos));
            if (success && baos.size() > 0) {
                JsonNode root = objectMapper.readTree(baos.toByteArray());
                if (root == null || !root.isObject()) {
                    return new HashMap<>();
                }
                JsonNode typesNode = root.has("types") && root.get("types").isObject() ? root.get("types") : root;
                Map<String, ActivePackageInfo> result = new HashMap<>();
                for (var entry : typesNode.properties()) {
                    String type = entry.getKey().toLowerCase();
                    ActivePackageInfo info = objectMapper.treeToValue(entry.getValue(), ActivePackageInfo.class);
                    if (info != null && info.version() != null && !info.version().isBlank()) {
                        result.put(type, info);
                    }
                }
                return result;
            }
        } catch (Exception e) {
            log.warn("Failed to read active.json at {}: {}", activePath, e.getMessage());
        }
        return new HashMap<>();
    }

    private String extractCreatedAt(SftpClient.DirEntry[] entries, MappingPackage.Meta metadata) {
        return (metadata != null && metadata.dateCreated() != null)
                ? metadata.dateCreated()
                : extractLatestFileTimestamp(entries);
    }

    // meta.package_type of the package, or the type folder name when it is missing; lowercase
    private String resolvePackageType(MappingPackage.Meta metadata, String typeFolderName) {
        String type = (metadata != null && metadata.packageType() != null && !metadata.packageType().isBlank())
                ? metadata.packageType().trim()
                : typeFolderName;
        return type.toLowerCase();
    }

    // First type folder of the latest version, even when its MPackage.json is missing or invalid
    private MappingPackageOverviewDto buildCompanyOverviewFallback(String companyName, String version) {
        String versionPath = SftpFolders.path(packagesRoot, companyName, version);
        List<String> types = folders.subfolders(versionPath);
        if (types.isEmpty()) {
            return null;
        }
        String typeName = types.get(0);
        String typePath = SftpFolders.path(versionPath, typeName);
        SftpClient.DirEntry[] typeEntries = folders.list(typePath);
        MappingPackage.Meta metadata = readMetadata(typePath, typeEntries);
        String createdAt = extractCreatedAt(typeEntries, metadata);
        String createdBy = metadata != null ? metadata.userCreated() : null;
        String customerName = metadata != null ? metadata.clientName() : null;
        String packageType = resolvePackageType(metadata, typeName);

        return new MappingPackageOverviewDto(
                companyName,
                version,
                createdAt,
                createdBy,
                customerName,
                packageType,
                version,
                createdAt,
                createdBy
        );
    }

    private static String displayName(MappingPackageOverviewDto p) {
        return (p.customerName() != null && !p.customerName().isBlank()) ? p.customerName() : p.company();
    }

    // Returns why the package data cannot be shown in the overview, or null when it is valid
    private String findMetadataProblem(MappingPackage.Meta metadata) {
        if (metadata == null) {
            return METADATA_FILENAME + " is missing, not valid JSON or has no \"meta\" block";
        }
        if (parseUploadTime(metadata.dateCreated()) == null) {
            return "creation time is missing or not an ISO 8601 timestamp";
        }
        return null;
    }

    // ISO 8601 time, e.g. 2026-10-22T14:05:00+02:00; a time without timezone is taken as UTC
    static Instant parseUploadTime(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        String text = value.trim();
        try {
            return OffsetDateTime.parse(text).toInstant();
        } catch (DateTimeParseException e) {
            try {
                return LocalDateTime.parse(text).toInstant(ZoneOffset.UTC);
            } catch (DateTimeParseException ignored) {
                return null;
            }
        }
    }

    private MappingPackage.Meta readMetadata(String typePath, SftpClient.DirEntry[] typeEntries) {
        String metadataFile = findMetadataFilename(typeEntries);
        if (metadataFile == null) {
            return null;
        }

        String metadataPath = SftpFolders.path(typePath, metadataFile);
        try {
            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            boolean success = template.get(metadataPath, in -> in.transferTo(baos));
            if (success && baos.size() > 0) {
                MappingPackage mappingPackage = objectMapper.readValue(baos.toByteArray(), MappingPackage.class);
                return mappingPackage != null ? mappingPackage.meta() : null;
            }
        } catch (Exception e) {
            log.warn("Failed to parse metadata file at {}: {}", metadataPath, e.getMessage());
        }
        return null;
    }

    // Actual filename of MPackage.json in the folder (case-insensitive match), or null
    private String findMetadataFilename(SftpClient.DirEntry[] entries) {
        for (SftpClient.DirEntry entry : entries) {
            if (METADATA_FILENAME.equalsIgnoreCase(entry.getFilename()) && !SftpFolders.isDirectory(entry)) {
                return entry.getFilename();
            }
        }
        return null;
    }

    // Newest modify time of the files in a package folder, used when the metadata has no creation time
    private String extractLatestFileTimestamp(SftpClient.DirEntry[] entries) {
        Instant latest = null;
        for (SftpClient.DirEntry entry : entries) {
            if (SftpFolders.isDirectory(entry) || entry.getAttributes() == null) {
                continue;
            }
            FileTime modifyTime = entry.getAttributes().getModifyTime();
            if (modifyTime != null && (latest == null || modifyTime.toInstant().isAfter(latest))) {
                latest = modifyTime.toInstant();
            }
        }
        return latest != null ? latest.toString() : null;
    }
}
