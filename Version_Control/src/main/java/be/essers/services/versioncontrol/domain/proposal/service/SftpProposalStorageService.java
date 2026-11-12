package be.essers.services.versioncontrol.domain.proposal.service;

import be.essers.services.versioncontrol.domain.proposal.api.dto.CompanyProposalOverviewDto;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDetailsDto;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalMetadata;
import be.essers.services.versioncontrol.infrastructure.sftp.SftpProperties;
import be.essers.services.versioncontrol.shared.exception.EntityNotFoundException;
import be.essers.services.versioncontrol.shared.exception.StorageException;
import tools.jackson.databind.ObjectMapper;
import org.apache.sshd.sftp.client.SftpClient;
import org.apache.sshd.sftp.common.SftpConstants;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;
import org.springframework.stereotype.Service;

import java.io.ByteArrayOutputStream;
import java.nio.file.attribute.FileTime;
import java.util.*;

@Service
public class SftpProposalStorageService implements ProposalStorageService {

    private static final Logger log = LoggerFactory.getLogger(SftpProposalStorageService.class);
    private static final String METADATA_FILENAME = "metadata.json";
    private static final String FALLBACK_METADATA_FILENAME = "proposal.json";
    private static final String EXCEL_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    private static final String EXCEL_XLS_MIME = "application/vnd.ms-excel";

    private final SftpRemoteFileTemplate template;
    private final SftpProperties properties;
    private final ObjectMapper objectMapper;

    public SftpProposalStorageService(SftpRemoteFileTemplate template, SftpProperties properties, ObjectMapper objectMapper) {
        this.template = template;
        this.properties = properties;
        this.objectMapper = objectMapper;
    }

    @Override
    public List<CompanyProposalOverviewDto> listProposals(String company) {
        try {
            if (company != null && !company.isBlank()) {
                String sanitized = sanitizePathSegment(company);
                CompanyProposalOverviewDto overview = getOverviewForCompany(sanitized);
                return List.of(overview);
            } else {
                return listAllProposals();
            }
        } catch (EntityNotFoundException | IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            log.error("Failed to list proposals from SFTP share at {}: {}", properties.basePath(), e.getMessage(), e);
            throw new StorageException("Unable to read proposals from SFTP storage: " + e.getMessage(), e);
        }
    }

    @Override
    public ProposalFileDetailsDto getProposalFile(String company, String version) {
        if (company == null || company.isBlank()) {
            throw new IllegalArgumentException("Company parameter must not be empty");
        }
        if (version == null || version.isBlank()) {
            throw new IllegalArgumentException("Version parameter must not be empty");
        }

        String sanitizedCompany = sanitizePathSegment(company);
        String sanitizedVersion = sanitizePathSegment(version);

        try {
            String rootPath = normalizePath(properties.basePath());
            String resolvedCompany = resolveDirectoryName(rootPath, sanitizedCompany);
            if (resolvedCompany == null) {
                throw new EntityNotFoundException("Company directory '" + company + "' does not exist");
            }

            String companyPath = rootPath + "/" + resolvedCompany;
            String resolvedVersion = resolveDirectoryName(companyPath, sanitizedVersion);
            if (resolvedVersion == null) {
                throw new EntityNotFoundException("Version directory '" + version + "' does not exist for company '" + resolvedCompany + "'");
            }

            String versionPath = companyPath + "/" + resolvedVersion;
            SftpClient.DirEntry[] versionEntries = template.list(versionPath);
            if (versionEntries == null || versionEntries.length == 0) {
                throw new EntityNotFoundException("No files found in directory '" + versionPath + "'");
            }

            ProposalMetadata metadata = readMetadata(versionPath, versionEntries);
            SftpClient.DirEntry excelEntry = findExcelEntry(versionEntries, metadata != null ? metadata.filename() : null);
            if (excelEntry == null) {
                throw new EntityNotFoundException("No Excel proposal file found for company '" + resolvedCompany + "' and version '" + resolvedVersion + "'");
            }

            String excelFilename = excelEntry.getFilename();
            String excelFullPath = versionPath + "/" + excelFilename;

            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            boolean readSuccess = template.get(excelFullPath, in -> in.transferTo(baos));
            if (!readSuccess) {
                throw new StorageException("Failed to read file from SFTP storage: " + excelFullPath);
            }

            byte[] fileBytes = baos.toByteArray();
            String base64Content = Base64.getEncoder().encodeToString(fileBytes);
            String contentType = getExcelContentType(excelFilename);

            String createdDate = (metadata != null && metadata.createdDate() != null)
                    ? metadata.createdDate()
                    : extractFileTimestamp(excelEntry);
            String createdBy = (metadata != null) ? metadata.createdBy() : null;
            String description = (metadata != null) ? metadata.description() : null;

            return new ProposalFileDetailsDto(
                    resolvedCompany,
                    resolvedVersion,
                    excelFilename,
                    excelFullPath,
                    contentType,
                    fileBytes.length,
                    createdDate,
                    createdBy,
                    description,
                    base64Content
            );
        } catch (EntityNotFoundException | IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            log.error("Failed to retrieve proposal file for company '{}' and version '{}': {}", company, version, e.getMessage(), e);
            throw new StorageException("Unable to read proposal file from SFTP storage: " + e.getMessage(), e);
        }
    }

    private CompanyProposalOverviewDto getOverviewForCompany(String company) {
        String rootPath = normalizePath(properties.basePath());
        String resolvedCompany = resolveDirectoryName(rootPath, company);
        if (resolvedCompany == null) {
            throw new EntityNotFoundException("Company directory '" + company + "' does not exist at " + rootPath);
        }

        CompanyProposalOverviewDto overview = buildCompanyOverview(rootPath, resolvedCompany);
        if (overview == null) {
            throw new EntityNotFoundException("No proposal versions found for company '" + resolvedCompany + "'");
        }
        return overview;
    }

    private List<CompanyProposalOverviewDto> listAllProposals() {
        String rootPath = normalizePath(properties.basePath());
        if (!template.exists(rootPath)) {
            log.warn("Root proposals directory '{}' does not exist on SFTP server", rootPath);
            return Collections.emptyList();
        }

        SftpClient.DirEntry[] entries = template.list(rootPath);
        if (entries == null || entries.length == 0) {
            return Collections.emptyList();
        }

        List<CompanyProposalOverviewDto> results = new ArrayList<>();
        for (SftpClient.DirEntry entry : entries) {
            String entryName = entry.getFilename();
            if (isSpecialDirectory(entryName) || !isDirectory(entry)) {
                continue;
            }

            CompanyProposalOverviewDto overview = buildCompanyOverview(rootPath, entryName);
            if (overview != null) {
                results.add(overview);
            }
        }

        results.sort(Comparator.comparing(CompanyProposalOverviewDto::company, String.CASE_INSENSITIVE_ORDER));
        return results;
    }

    private CompanyProposalOverviewDto buildCompanyOverview(String rootPath, String companyName) {
        String companyPath = rootPath + "/" + companyName;
        SftpClient.DirEntry[] companyEntries = template.list(companyPath);
        if (companyEntries == null || companyEntries.length == 0) {
            return null;
        }

        List<String> versions = new ArrayList<>();
        for (SftpClient.DirEntry entry : companyEntries) {
            String name = entry.getFilename();
            if (!isSpecialDirectory(name) && isDirectory(entry)) {
                versions.add(name);
            }
        }

        if (versions.isEmpty()) {
            return null;
        }

        versions.sort(VersionComparator.INSTANCE);
        String latestVersion = versions.get(versions.size() - 1);

        String versionPath = companyPath + "/" + latestVersion;
        SftpClient.DirEntry[] versionEntries = template.list(versionPath);
        if (versionEntries == null) {
            versionEntries = new SftpClient.DirEntry[0];
        }

        ProposalMetadata metadata = readMetadata(versionPath, versionEntries);
        SftpClient.DirEntry excelEntry = findExcelEntry(versionEntries, metadata != null ? metadata.filename() : null);

        String filename = (excelEntry != null)
                ? excelEntry.getFilename()
                : (metadata != null ? metadata.filename() : null);
        String fullPath = (filename != null) ? versionPath + "/" + filename : null;

        String createdDate = (metadata != null && metadata.createdDate() != null)
                ? metadata.createdDate()
                : (excelEntry != null ? extractFileTimestamp(excelEntry) : null);
        String createdBy = (metadata != null) ? metadata.createdBy() : null;
        String description = (metadata != null) ? metadata.description() : null;
        String status = (metadata != null) ? metadata.status() : null;
        String aiStatus = (metadata != null) ? metadata.aiStatus() : null;

        return new CompanyProposalOverviewDto(
                companyName,
                latestVersion,
                filename,
                fullPath,
                createdDate,
                createdBy,
                description,
                status,
                aiStatus
        );
    }

    private ProposalMetadata readMetadata(String versionPath, SftpClient.DirEntry[] versionEntries) {
        String metadataFile = resolveMetadataFilename(versionPath, versionEntries);
        if (metadataFile == null) {
            return null;
        }

        String metadataPath = versionPath + "/" + metadataFile;
        try {
            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            boolean success = template.get(metadataPath, in -> in.transferTo(baos));
            if (success && baos.size() > 0) {
                return objectMapper.readValue(baos.toByteArray(), ProposalMetadata.class);
            }
        } catch (Exception e) {
            log.warn("Failed to parse metadata file at {}: {}", metadataPath, e.getMessage());
        }
        return null;
    }

    private String resolveMetadataFilename(String versionPath, SftpClient.DirEntry[] versionEntries) {
        if (versionEntries != null && versionEntries.length > 0) {
            for (SftpClient.DirEntry entry : versionEntries) {
                if (METADATA_FILENAME.equalsIgnoreCase(entry.getFilename()) && !isDirectory(entry)) {
                    return entry.getFilename();
                }
            }
            for (SftpClient.DirEntry entry : versionEntries) {
                if (FALLBACK_METADATA_FILENAME.equalsIgnoreCase(entry.getFilename()) && !isDirectory(entry)) {
                    return entry.getFilename();
                }
            }
            return null;
        }
        if (template.exists(versionPath + "/" + METADATA_FILENAME)) {
            return METADATA_FILENAME;
        }
        if (template.exists(versionPath + "/" + FALLBACK_METADATA_FILENAME)) {
            return FALLBACK_METADATA_FILENAME;
        }
        return null;
    }

    private SftpClient.DirEntry findExcelEntry(SftpClient.DirEntry[] entries, String preferredFilename) {
        if (entries == null || entries.length == 0) {
            return null;
        }

        if (preferredFilename != null && !preferredFilename.isBlank()) {
            for (SftpClient.DirEntry entry : entries) {
                if (!isDirectory(entry) && preferredFilename.equalsIgnoreCase(entry.getFilename())) {
                    return entry;
                }
            }
        }

        for (SftpClient.DirEntry entry : entries) {
            if (!isDirectory(entry)) {
                String name = entry.getFilename().toLowerCase();
                if (name.endsWith(".xlsx") || name.endsWith(".xls")) {
                    return entry;
                }
            }
        }

        return null;
    }

    private String resolveDirectoryName(String parentPath, String targetName) {
        String exactPath = parentPath + "/" + targetName;
        if (template.exists(exactPath)) {
            return targetName;
        }

        SftpClient.DirEntry[] entries = template.list(parentPath);
        if (entries != null) {
            for (SftpClient.DirEntry entry : entries) {
                if (isDirectory(entry) && entry.getFilename().equalsIgnoreCase(targetName)) {
                    return entry.getFilename();
                }
            }
        }
        return null;
    }

    private String extractFileTimestamp(SftpClient.DirEntry entry) {
        if (entry == null || entry.getAttributes() == null) {
            return null;
        }
        FileTime createTime = entry.getAttributes().getCreateTime();
        if (createTime != null) {
            return createTime.toInstant().toString();
        }
        FileTime modifyTime = entry.getAttributes().getModifyTime();
        if (modifyTime != null) {
            return modifyTime.toInstant().toString();
        }
        return null;
    }

    private String getExcelContentType(String filename) {
        if (filename != null && filename.toLowerCase().endsWith(".xlsx")) {
            return EXCEL_XLSX_MIME;
        }
        return EXCEL_XLS_MIME;
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

    private String normalizePath(String path) {
        if (path == null || path.isBlank()) {
            return "/Proposals";
        }
        String trimmed = path.trim();
        if (trimmed.endsWith("/")) {
            return trimmed.substring(0, trimmed.length() - 1);
        }
        return trimmed;
    }
}
