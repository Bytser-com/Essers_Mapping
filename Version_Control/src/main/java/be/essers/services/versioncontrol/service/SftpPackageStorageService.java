package be.essers.services.versioncontrol.service;

import be.essers.services.versioncontrol.domain.dto.MappingPackageOverviewDto;
import be.essers.services.versioncontrol.domain.dto.MappingPackage;
import be.essers.services.versioncontrol.exception.EntityNotFoundException;
import be.essers.services.versioncontrol.exception.StorageException;
import tools.jackson.databind.ObjectMapper;
import org.apache.sshd.sftp.client.SftpClient;
import org.apache.sshd.sftp.common.SftpConstants;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;
import org.springframework.stereotype.Service;

import java.io.ByteArrayOutputStream;
import java.nio.file.attribute.FileTime;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeParseException;
import java.util.*;

/**
 * Reads mapping packages from SFTP. Layout:
 * {@code <sftp.packages-path>/<companyName>/<version>/<type>/MPackage.json}
 */
@Service
public class SftpPackageStorageService implements PackageStorageService {

    private static final Logger log = LoggerFactory.getLogger(SftpPackageStorageService.class);

    private static final String METADATA_FILENAME = "MPackage.json";
    private static final int MAX_COMPANY_LENGTH = 20;

    // Alphabetical on the name shown in the list (customerName, or the company folder), then on the type
    private static final Comparator<MappingPackageOverviewDto> ALPHABETICAL = Comparator
            .comparing((MappingPackageOverviewDto p) -> displayName(p), String.CASE_INSENSITIVE_ORDER)
            .thenComparing(p -> p.packageType() != null ? p.packageType() : "", String.CASE_INSENSITIVE_ORDER);

    private final SftpRemoteFileTemplate template;
    private final String packagesRoot;
    private final ObjectMapper objectMapper;

    public SftpPackageStorageService(SftpRemoteFileTemplate template, ObjectMapper objectMapper,
                                     @Value("${sftp.packages-path:/Packages}") String packagesRoot) {
        this.template = template;
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
                String sanitized = sanitizePathSegment(company);
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

    private List<MappingPackageOverviewDto> getOverviewsForCompany(String company) {
        String resolvedCompany = resolveDirectoryName(packagesRoot, company);
        if (resolvedCompany == null) {
            throw new EntityNotFoundException("Company directory '" + company + "' does not exist at " + packagesRoot);
        }

        String companyPath = packagesRoot + "/" + resolvedCompany;
        List<String> versions = listSubdirectories(companyPath);
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
        if (!template.exists(packagesRoot)) {
            log.warn("Root packages directory '{}' does not exist on SFTP server", packagesRoot);
            return Collections.emptyList();
        }

        List<MappingPackageOverviewDto> results = new ArrayList<>();
        for (String companyName : listSubdirectories(packagesRoot)) {
            List<String> versions = listSubdirectories(packagesRoot + "/" + companyName);
            versions.sort(VersionComparator.INSTANCE);
            results.addAll(findLatestPackagesForCompany(companyName, versions));
        }

        results.sort(ALPHABETICAL);
        return results;
    }

    /**
     * Walks the versions from newest to oldest and returns one overview per package type:
     * for every type the company has, the newest version with a valid MPackage.json.
     * A type that only exists in an older version is still returned (with that older version).
     */
    private List<MappingPackageOverviewDto> findLatestPackagesForCompany(String companyName, List<String> versions) {
        String companyPath = packagesRoot + "/" + companyName;
        Map<String, MappingPackageOverviewDto> latestByType = new LinkedHashMap<>();

        for (int i = versions.size() - 1; i >= 0; i--) {
            String version = versions.get(i);
            String versionPath = companyPath + "/" + version;

            for (String typeName : listSubdirectories(versionPath)) {
                String typePath = versionPath + "/" + typeName;
                SftpClient.DirEntry[] typeEntries = listEntries(typePath);
                MappingPackage.Meta metadata = readMetadata(typePath, typeEntries);
                String problem = findMetadataProblem(metadata);
                if (problem != null) {
                    log.warn("Skipping package {}: {}", typePath, problem);
                    continue;
                }
                String packageType = resolvePackageType(metadata, typeName);
                // Versions are walked newest first, so the first package of a type is its latest
                latestByType.putIfAbsent(packageType,
                        toOverview(companyName, version, packageType, typeEntries, metadata));
            }
        }

        return new ArrayList<>(latestByType.values());
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
        String versionPath = packagesRoot + "/" + companyName + "/" + version;
        List<String> types = listSubdirectories(versionPath);
        if (types.isEmpty()) {
            return null;
        }
        String typeName = types.get(0);
        String typePath = versionPath + "/" + typeName;
        SftpClient.DirEntry[] typeEntries = listEntries(typePath);
        MappingPackage.Meta metadata = readMetadata(typePath, typeEntries);
        return toOverview(companyName, version, resolvePackageType(metadata, typeName), typeEntries, metadata);
    }

    private MappingPackageOverviewDto toOverview(String companyName, String version, String packageType,
                                                 SftpClient.DirEntry[] entries, MappingPackage.Meta metadata) {
        String createdAt = (metadata != null && metadata.dateCreated() != null)
                ? metadata.dateCreated()
                : extractLatestFileTimestamp(entries);
        String createdBy = (metadata != null) ? metadata.userCreated() : null;
        String customerName = (metadata != null) ? metadata.clientName() : null;

        return new MappingPackageOverviewDto(
                companyName,
                version,
                createdAt,
                createdBy,
                customerName,
                packageType
        );
    }

    private static String displayName(MappingPackageOverviewDto p) {
        return (p.customerName() != null && !p.customerName().isBlank()) ? p.customerName() : p.company();
    }

    // Names of the subdirectories of a path (without "." and "..")
    private List<String> listSubdirectories(String path) {
        List<String> names = new ArrayList<>();
        for (SftpClient.DirEntry entry : listEntries(path)) {
            if (!isSpecialDirectory(entry.getFilename()) && isDirectory(entry)) {
                names.add(entry.getFilename());
            }
        }
        return names;
    }

    private SftpClient.DirEntry[] listEntries(String path) {
        SftpClient.DirEntry[] entries = template.list(path);
        return entries != null ? entries : new SftpClient.DirEntry[0];
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

        String metadataPath = typePath + "/" + metadataFile;
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
            if (METADATA_FILENAME.equalsIgnoreCase(entry.getFilename()) && !isDirectory(entry)) {
                return entry.getFilename();
            }
        }
        return null;
    }

    // Newest modify time of the files in a package folder, used when the metadata has no creation time
    private String extractLatestFileTimestamp(SftpClient.DirEntry[] entries) {
        Instant latest = null;
        for (SftpClient.DirEntry entry : entries) {
            if (isDirectory(entry) || entry.getAttributes() == null) {
                continue;
            }
            FileTime modifyTime = entry.getAttributes().getModifyTime();
            if (modifyTime != null && (latest == null || modifyTime.toInstant().isAfter(latest))) {
                latest = modifyTime.toInstant();
            }
        }
        return latest != null ? latest.toString() : null;
    }

    private String resolveDirectoryName(String parentPath, String targetName) {
        if (template.exists(parentPath + "/" + targetName)) {
            return targetName;
        }
        for (String name : listSubdirectories(parentPath)) {
            if (name.equalsIgnoreCase(targetName)) {
                return name;
            }
        }
        return null;
    }

    private boolean isSpecialDirectory(String name) {
        return ".".equals(name) || "..".equals(name);
    }

    private boolean isDirectory(SftpClient.DirEntry entry) {
        if (entry.getAttributes() == null) {
            return false;
        }
        return entry.getAttributes().isDirectory()
                || entry.getAttributes().getType() == SftpConstants.SSH_FILEXFER_TYPE_DIRECTORY;
    }

    private String sanitizePathSegment(String segment) {
        String trimmed = segment.trim();
        if (trimmed.contains("/") || trimmed.contains("\\") || trimmed.contains("..")) {
            throw new IllegalArgumentException("Path segment contains illegal characters: " + segment);
        }
        return trimmed;
    }
}
