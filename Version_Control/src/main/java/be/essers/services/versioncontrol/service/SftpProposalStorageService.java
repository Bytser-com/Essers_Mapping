package be.essers.services.versioncontrol.service;

import be.essers.services.versioncontrol.config.SftpProperties;
import be.essers.services.versioncontrol.domain.dto.CompanyProposalOverviewDto;
import be.essers.services.versioncontrol.domain.dto.ProposalFileDataDto;
import be.essers.services.versioncontrol.domain.dto.ProposalFileDetailsDto;
import be.essers.services.versioncontrol.domain.dto.ProposalMetadata;
import be.essers.services.versioncontrol.domain.dto.ProposalRowDto;
import be.essers.services.versioncontrol.exception.EntityNotFoundException;
import be.essers.services.versioncontrol.exception.StorageException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.ss.usermodel.WorkbookFactory;
import org.apache.sshd.sftp.client.SftpClient;
import org.apache.sshd.sftp.common.SftpConstants;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.file.remote.session.Session;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;
import org.springframework.stereotype.Service;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.file.attribute.FileTime;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.*;

@Service
public class SftpProposalStorageService implements ProposalStorageService {

    private static final Logger log = LoggerFactory.getLogger(SftpProposalStorageService.class);
    private static final String METADATA_FILENAME = "metadata.json";
    private static final String FALLBACK_METADATA_FILENAME = "proposal.json";
    private static final String EXCEL_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    private static final String EXCEL_XLS_MIME = "application/vnd.ms-excel";
    private static final int MAX_COMPANY_LENGTH = 20;
    private static final int MAX_PROPOSAL_TYPE_LENGTH = 20;
    // Statuses the overview can show (same values as Mapping_Proposal writes in proposal.json)
    private static final Set<String> PROPOSAL_STATUSES =
            Set.of("AI_GENERATING", "READY_FOR_REVIEW", "IN_REVIEW", "In review", "AI_CHECKING_REVIEW", "RETURNED");
    private static final Set<String> AI_STATUSES = Set.of("RUNNING", "FAILED");

    private final SftpRemoteFileTemplate template;
    private final SftpProperties properties;
    private final ObjectMapper objectMapper;
    private final ExcelProposalParser excelProposalParser;

    @org.springframework.beans.factory.annotation.Autowired
    public SftpProposalStorageService(@org.springframework.beans.factory.annotation.Qualifier("sftpRemoteFileTemplate") SftpRemoteFileTemplate template,
                                      SftpProperties properties,
                                      ObjectMapper objectMapper,
                                      ExcelProposalParser excelProposalParser) {
        this.template = template;
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.excelProposalParser = excelProposalParser != null ? excelProposalParser : new ExcelProposalParser();
    }

    public SftpProposalStorageService(SftpRemoteFileTemplate template, SftpProperties properties, ObjectMapper objectMapper) {
        this(template, properties, objectMapper, new ExcelProposalParser());
    }

    @Override
    public List<CompanyProposalOverviewDto> listProposals(String company) {
        return listProposals(company, null);
    }

    @Override
    public List<CompanyProposalOverviewDto> listProposals(String company, String proposalType) {
        try {
            if (company != null && !company.isBlank()) {
                if (company.length() > MAX_COMPANY_LENGTH) {
                    throw new IllegalArgumentException("Company parameter must not exceed " + MAX_COMPANY_LENGTH + " characters");
                }
                String sanitized = sanitizePathSegment(company);
                String sanitizedType = null;
                if (proposalType != null && !proposalType.isBlank()) {
                    if (proposalType.length() > MAX_PROPOSAL_TYPE_LENGTH) {
                        throw new IllegalArgumentException("Proposal type parameter must not exceed " + MAX_PROPOSAL_TYPE_LENGTH + " characters");
                    }
                    sanitizedType = sanitizePathSegment(proposalType).toLowerCase();
                }
                return getOverviewsForCompany(sanitized, sanitizedType);
            } else {
                String sanitizedType = null;
                if (proposalType != null && !proposalType.isBlank()) {
                    if (proposalType.length() > MAX_PROPOSAL_TYPE_LENGTH) {
                        throw new IllegalArgumentException("Proposal type parameter must not exceed " + MAX_PROPOSAL_TYPE_LENGTH + " characters");
                    }
                    sanitizedType = sanitizePathSegment(proposalType).toLowerCase();
                }
                return listAllProposals(sanitizedType);
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
        return getProposalFile(company, version, null);
    }

    @Override
    public ProposalFileDetailsDto getProposalFile(String company, String version, String proposalType) {
        validateCompany(company);
        validateVersion(version);
        validateProposalTypeIfPresent(proposalType);

        String sanitizedCompany = sanitizePathSegment(company);
        String sanitizedVersion = sanitizePathSegment(version);
        String sanitizedProposalType = (proposalType != null && !proposalType.isBlank())
                ? sanitizePathSegment(proposalType).toLowerCase()
                : null;

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
            String targetPath = null;
            String resolvedProposalType = null;

            if (sanitizedProposalType != null) {
                resolvedProposalType = resolveDirectoryName(versionPath, sanitizedProposalType);
                if (resolvedProposalType != null) {
                    targetPath = versionPath + "/" + resolvedProposalType;
                } else if (template.exists(versionPath + "/" + METADATA_FILENAME) || template.exists(versionPath + "/" + FALLBACK_METADATA_FILENAME)) {
                    targetPath = versionPath;
                } else {
                    throw new EntityNotFoundException("Proposal type directory '" + proposalType + "' does not exist for company '" + resolvedCompany + "' and version '" + resolvedVersion + "'");
                }
            } else {
                SftpClient.DirEntry[] vEntries = template.list(versionPath);
                if (vEntries != null) {
                    for (SftpClient.DirEntry entry : vEntries) {
                        if (!isSpecialDirectory(entry.getFilename()) && isDirectory(entry)) {
                            targetPath = versionPath + "/" + entry.getFilename();
                            resolvedProposalType = entry.getFilename();
                            break;
                        }
                    }
                }
                if (targetPath == null) {
                    targetPath = versionPath;
                }
            }

            SftpClient.DirEntry[] folderEntries = template.list(targetPath);
            if (folderEntries == null || folderEntries.length == 0) {
                throw new EntityNotFoundException("No files found in directory '" + targetPath + "'");
            }

            ProposalMetadata metadata = readMetadata(targetPath, folderEntries);
            SftpClient.DirEntry excelEntry = findExcelEntry(folderEntries, metadata != null ? metadata.filename() : null);
            if (excelEntry == null) {
                throw new EntityNotFoundException("No Excel proposal file found for company '" + resolvedCompany + "' and version '" + resolvedVersion + "'");
            }

            String excelFilename = excelEntry.getFilename();
            String excelFullPath = targetPath + "/" + excelFilename;

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
            String finalProposalType = (resolvedProposalType != null)
                    ? resolvedProposalType.toLowerCase()
                    : (metadata != null && metadata.proposalType() != null ? metadata.proposalType().toLowerCase() : (proposalType != null ? proposalType.toLowerCase() : null));

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
                    base64Content,
                    finalProposalType
            );
        } catch (EntityNotFoundException | IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            log.error("Failed to retrieve proposal file for company '{}' and version '{}': {}", company, version, e.getMessage(), e);
            throw new StorageException("Unable to read proposal file from SFTP storage: " + e.getMessage(), e);
        }
    }

    @Override
    public ProposalFileDataDto getProposalFileData(String company, String version) {
        return getProposalFileData(company, version, null);
    }

    @Override
    public ProposalFileDataDto getProposalFileData(String company, String version, String proposalType) {
        validateCompany(company);
        validateVersion(version);
        validateProposalTypeIfPresent(proposalType);

        String sanitizedCompany = sanitizePathSegment(company);
        String sanitizedVersion = sanitizePathSegment(version);
        String sanitizedProposalType = (proposalType != null && !proposalType.isBlank())
                ? sanitizePathSegment(proposalType).toLowerCase()
                : null;

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
            String targetPath = null;
            String resolvedProposalType = null;

            if (sanitizedProposalType != null) {
                resolvedProposalType = resolveDirectoryName(versionPath, sanitizedProposalType);
                if (resolvedProposalType != null) {
                    targetPath = versionPath + "/" + resolvedProposalType;
                } else if (template.exists(versionPath + "/" + METADATA_FILENAME) || template.exists(versionPath + "/" + FALLBACK_METADATA_FILENAME)) {
                    targetPath = versionPath;
                } else {
                    throw new EntityNotFoundException("Proposal type directory '" + proposalType + "' does not exist for company '" + resolvedCompany + "' and version '" + resolvedVersion + "'");
                }
            } else {
                SftpClient.DirEntry[] vEntries = template.list(versionPath);
                if (vEntries != null) {
                    for (SftpClient.DirEntry entry : vEntries) {
                        if (!isSpecialDirectory(entry.getFilename()) && isDirectory(entry)) {
                            targetPath = versionPath + "/" + entry.getFilename();
                            resolvedProposalType = entry.getFilename();
                            break;
                        }
                    }
                }
                if (targetPath == null) {
                    targetPath = versionPath;
                }
            }

            SftpClient.DirEntry[] folderEntries = template.list(targetPath);
            if (folderEntries == null || folderEntries.length == 0) {
                throw new EntityNotFoundException("No files found in directory '" + targetPath + "'");
            }

            ProposalMetadata metadata = readMetadata(targetPath, folderEntries);
            SftpClient.DirEntry excelEntry = findExcelEntry(folderEntries, metadata != null ? metadata.filename() : null);
            if (excelEntry == null) {
                throw new EntityNotFoundException("No Excel proposal file found for company '" + resolvedCompany + "' and version '" + resolvedVersion + "'");
            }

            String excelFilename = excelEntry.getFilename();
            String excelFullPath = targetPath + "/" + excelFilename;

            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            boolean readSuccess = template.get(excelFullPath, in -> in.transferTo(baos));
            if (!readSuccess) {
                throw new StorageException("Failed to read file from SFTP storage: " + excelFullPath);
            }

            List<ProposalRowDto> rows = excelProposalParser.parseProposalRows(new ByteArrayInputStream(baos.toByteArray()));

            String companyName = (metadata != null && metadata.company() != null && !metadata.company().isBlank())
                    ? metadata.company()
                    : resolvedCompany;

            String uploadTimestamp = (metadata != null && metadata.createdDate() != null)
                    ? metadata.createdDate()
                    : extractFileTimestamp(excelEntry);

            String[] uploadParts = parseDateAndTime(uploadTimestamp);
            String uploadDate = uploadParts[0];
            String uploadTime = uploadParts[1];

            String updateTimestamp = (metadata != null && metadata.updatedAt() != null)
                    ? metadata.updatedAt()
                    : extractFileModifyTimestamp(excelEntry);

            String[] updateParts = parseDateAndTime(updateTimestamp);
            String updatedDate = updateParts[0];
            String updatedTime = updateParts[1];

            String createdBy = (metadata != null) ? metadata.createdBy() : null;
            String status = (metadata != null) ? metadata.status() : null;
            Object aiReview = (metadata != null) ? metadata.aiReview() : null;
            String finalProposalType = (resolvedProposalType != null)
                    ? resolvedProposalType.toLowerCase()
                    : (metadata != null && metadata.proposalType() != null ? metadata.proposalType().toLowerCase() : (proposalType != null ? proposalType.toLowerCase() : null));

            return new ProposalFileDataDto(
                    resolvedVersion,
                    companyName,
                    finalProposalType,
                    uploadDate,
                    uploadTime,
                    updatedTime,
                    updatedDate,
                    createdBy,
                    status,
                    rows,
                    aiReview
            );
        } catch (EntityNotFoundException | IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            log.error("Failed to retrieve proposal file data for company '{}' and version '{}': {}", company, version, e.getMessage(), e);
            throw new StorageException("Unable to read proposal file data from SFTP storage: " + e.getMessage(), e);
        }
    }

    @Override
    public ProposalFileDetailsDto overwriteProposalFile(String company, String version, byte[] fileBytes, String originalFilename) {
        return overwriteProposalFile(company, version, null, fileBytes, originalFilename);
    }

    @Override
    public ProposalFileDetailsDto overwriteProposalFile(String company, String version, String proposalType, byte[] fileBytes, String originalFilename) {
        validateCompany(company);
        validateVersion(version);
        validateProposalTypeIfPresent(proposalType);
        if (fileBytes == null || fileBytes.length == 0) {
            throw new IllegalArgumentException("File content must not be empty");
        }

        validateExcelBytes(fileBytes);

        String sanitizedCompany = sanitizePathSegment(company);
        String sanitizedVersion = sanitizePathSegment(version);
        String sanitizedProposalType = (proposalType != null && !proposalType.isBlank())
                ? sanitizePathSegment(proposalType).toLowerCase()
                : null;

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
            String targetFolderPath = null;
            String resolvedProposalType = null;

            if (sanitizedProposalType != null) {
                resolvedProposalType = resolveDirectoryName(versionPath, sanitizedProposalType);
                if (resolvedProposalType != null) {
                    targetFolderPath = versionPath + "/" + resolvedProposalType;
                } else if (template.exists(versionPath + "/" + METADATA_FILENAME) || template.exists(versionPath + "/" + FALLBACK_METADATA_FILENAME)) {
                    targetFolderPath = versionPath;
                } else {
                    throw new EntityNotFoundException("Proposal type directory '" + proposalType + "' does not exist for company '" + resolvedCompany + "' and version '" + resolvedVersion + "'");
                }
            } else {
                SftpClient.DirEntry[] vEntries = template.list(versionPath);
                if (vEntries != null) {
                    for (SftpClient.DirEntry entry : vEntries) {
                        if (!isSpecialDirectory(entry.getFilename()) && isDirectory(entry)) {
                            targetFolderPath = versionPath + "/" + entry.getFilename();
                            resolvedProposalType = entry.getFilename();
                            break;
                        }
                    }
                }
                if (targetFolderPath == null) {
                    targetFolderPath = versionPath;
                }
            }

            SftpClient.DirEntry[] folderEntries = template.list(targetFolderPath);
            if (folderEntries == null || folderEntries.length == 0) {
                throw new EntityNotFoundException("No files found in directory '" + targetFolderPath + "'");
            }

            ProposalMetadata metadata = readMetadata(targetFolderPath, folderEntries);
            SftpClient.DirEntry existingExcelEntry = findExcelEntry(folderEntries, metadata != null ? metadata.filename() : null);

            String targetFilename;
            if (existingExcelEntry != null) {
                targetFilename = existingExcelEntry.getFilename();
            } else if (originalFilename != null && !originalFilename.isBlank()) {
                targetFilename = sanitizePathSegment(originalFilename);
            } else {
                targetFilename = "mappingproposal.xlsx";
            }

            String targetFullPath = targetFolderPath + "/" + targetFilename;

            // 1. Write the new Excel file to SFTP (overwriting existing file)
            template.execute(session -> {
                session.write(new ByteArrayInputStream(fileBytes), targetFullPath);
                return null;
            });

            // 2. Update metadata: updated_time, updated_date, and status = "In review"
            OffsetDateTime now = OffsetDateTime.now(ZoneOffset.UTC);
            String nowIso = now.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME);
            String nowDate = now.toLocalDate().toString();
            String nowTime = now.toLocalTime().format(DateTimeFormatter.ofPattern("HH:mm:ss"));

            String metadataFileName = resolveMetadataFilename(targetFolderPath, folderEntries);
            if (metadataFileName == null) {
                metadataFileName = METADATA_FILENAME;
            }
            String metadataFullPath = targetFolderPath + "/" + metadataFileName;

            // Read existing metadata raw JSON if possible, else create new
            ByteArrayOutputStream metaBaos = new ByteArrayOutputStream();
            boolean metaRead = template.get(metadataFullPath, in -> in.transferTo(metaBaos));

            ObjectNode rootNode;
            if (metaRead && metaBaos.size() > 0) {
                try {
                    JsonNode parsed = objectMapper.readTree(metaBaos.toByteArray());
                    rootNode = parsed.isObject() ? (ObjectNode) parsed : objectMapper.createObjectNode();
                } catch (Exception e) {
                    log.warn("Failed to parse existing metadata JSON at {}, recreating: {}", metadataFullPath, e.getMessage());
                    rootNode = objectMapper.createObjectNode();
                }
            } else {
                rootNode = objectMapper.createObjectNode();
            }

            rootNode.put("status", "In review");
            rootNode.put("updated_at", nowIso);
            rootNode.put("updated_date", nowDate);
            rootNode.put("updated_time", nowTime);
            rootNode.put("filename", targetFilename);
            String effectiveType = (resolvedProposalType != null)
                    ? resolvedProposalType.toLowerCase()
                    : (proposalType != null ? proposalType.toLowerCase() : (metadata != null && metadata.proposalType() != null ? metadata.proposalType().toLowerCase() : null));
            if (effectiveType != null) {
                rootNode.put("proposal_type", effectiveType.toLowerCase());
                rootNode.put("proposalType", effectiveType.toLowerCase());
            }
            if (!rootNode.has("customer") && !rootNode.has("company")) {
                rootNode.put("company", resolvedCompany);
                rootNode.put("customer", resolvedCompany);
            }
            if (!rootNode.has("version")) {
                rootNode.put("version", resolvedVersion);
            }
            if (!rootNode.has("createdDate") && !rootNode.has("uploaded_at")) {
                rootNode.put("createdDate", nowIso);
                rootNode.put("uploaded_at", nowIso);
            }

            byte[] updatedMetaBytes = objectMapper.writerWithDefaultPrettyPrinter().writeValueAsBytes(rootNode);
            template.execute(session -> {
                session.write(new ByteArrayInputStream(updatedMetaBytes), metadataFullPath);
                return null;
            });

            // 3. Return updated ProposalFileDetailsDto
            String base64Content = Base64.getEncoder().encodeToString(fileBytes);
            String contentType = getExcelContentType(targetFilename);
            String createdDate = (metadata != null && metadata.createdDate() != null)
                    ? metadata.createdDate()
                    : (existingExcelEntry != null ? extractFileTimestamp(existingExcelEntry) : nowIso);
            String createdBy = (metadata != null) ? metadata.createdBy() : null;
            String description = (metadata != null) ? metadata.description() : null;

            return new ProposalFileDetailsDto(
                    resolvedCompany,
                    resolvedVersion,
                    targetFilename,
                    targetFullPath,
                    contentType,
                    fileBytes.length,
                    createdDate,
                    createdBy,
                    description,
                    base64Content,
                    effectiveType
            );
        } catch (EntityNotFoundException | IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            log.error("Failed to overwrite proposal file for company '{}' and version '{}': {}", company, version, e.getMessage(), e);
            throw new StorageException("Unable to overwrite proposal file on SFTP storage: " + e.getMessage(), e);
        }
    }

    @Override
    public void deleteProposal(String company, String version) {
        deleteProposal(company, version, null);
    }

    @Override
    public void deleteProposal(String company, String version, String proposalType) {
        validateCompany(company);
        validateVersion(version);
        validateProposalTypeIfPresent(proposalType);

        String sanitizedCompany = sanitizePathSegment(company);
        String sanitizedVersion = sanitizePathSegment(version);
        String sanitizedProposalType = (proposalType != null && !proposalType.isBlank())
                ? sanitizePathSegment(proposalType).toLowerCase()
                : null;

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
            String targetDeletePath;
            boolean isTypeSubdir = false;

            if (sanitizedProposalType != null) {
                String resolvedProposalType = resolveDirectoryName(versionPath, sanitizedProposalType);
                if (resolvedProposalType != null) {
                    targetDeletePath = versionPath + "/" + resolvedProposalType;
                    isTypeSubdir = true;
                } else if (template.exists(versionPath + "/" + METADATA_FILENAME) || template.exists(versionPath + "/" + FALLBACK_METADATA_FILENAME)) {
                    targetDeletePath = versionPath;
                } else {
                    throw new EntityNotFoundException("Proposal type directory '" + proposalType + "' does not exist for company '" + resolvedCompany + "' and version '" + resolvedVersion + "'");
                }
            } else {
                targetDeletePath = versionPath;
            }

            SftpClient.DirEntry[] targetEntries = template.list(targetDeletePath);
            boolean finalIsTypeSubdir = isTypeSubdir;

            template.execute(session -> {
                if (targetEntries != null) {
                    for (SftpClient.DirEntry entry : targetEntries) {
                        String name = entry.getFilename();
                        if (isSpecialDirectory(name)) {
                            continue;
                        }
                        String childPath = targetDeletePath + "/" + name;
                        if (isDirectory(entry)) {
                            deleteRecursively(session, childPath);
                        } else {
                            session.remove(childPath);
                        }
                    }
                }
                session.rmdir(targetDeletePath);

                // If deleted a type subdirectory, clean up empty version directory if no other entries remain
                if (finalIsTypeSubdir) {
                    SftpClient.DirEntry[] remainingInVersion = template.list(versionPath);
                    boolean versionEmpty = true;
                    if (remainingInVersion != null) {
                        for (SftpClient.DirEntry entry : remainingInVersion) {
                            if (!isSpecialDirectory(entry.getFilename())) {
                                versionEmpty = false;
                                break;
                            }
                        }
                    }
                    if (versionEmpty) {
                        try {
                            session.rmdir(versionPath);
                            log.info("Cleaned up empty version directory '{}'", versionPath);
                        } catch (Exception ex) {
                            log.warn("Could not remove empty version directory '{}': {}", versionPath, ex.getMessage());
                        }
                    }
                }

                // Clean up empty company directory if no other versions/files remain
                SftpClient.DirEntry[] remaining = template.list(companyPath);
                boolean isEmpty = true;
                if (remaining != null) {
                    for (SftpClient.DirEntry entry : remaining) {
                        if (!isSpecialDirectory(entry.getFilename())) {
                            isEmpty = false;
                            break;
                        }
                    }
                }
                if (isEmpty) {
                    try {
                        session.rmdir(companyPath);
                        log.info("Cleaned up empty company directory '{}'", companyPath);
                    } catch (Exception ex) {
                        log.warn("Could not remove empty company directory '{}': {}", companyPath, ex.getMessage());
                    }
                }
                return null;
            });

            log.info("Successfully deleted proposal directory '{}' from SFTP", targetDeletePath);
        } catch (EntityNotFoundException | IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            log.error("Failed to delete proposal for company '{}' and version '{}': {}", company, version, e.getMessage(), e);
            throw new StorageException("Unable to delete proposal from SFTP storage: " + e.getMessage(), e);
        }
    }

    private void deleteRecursively(Session<SftpClient.DirEntry> session, String path) throws IOException {
        SftpClient.DirEntry[] entries = session.list(path);
        if (entries != null) {
            for (SftpClient.DirEntry entry : entries) {
                String name = entry.getFilename();
                if (isSpecialDirectory(name)) {
                    continue;
                }
                String childPath = path + "/" + name;
                if (isDirectory(entry)) {
                    deleteRecursively(session, childPath);
                } else {
                    session.remove(childPath);
                }
            }
        }
        session.rmdir(path);
    }

    private void validateExcelBytes(byte[] fileBytes) {
        try (Workbook wb = WorkbookFactory.create(new ByteArrayInputStream(fileBytes))) {
            if (wb.getNumberOfSheets() == 0) {
                throw new IllegalArgumentException("Uploaded Excel file has no sheets");
            }
        } catch (IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalArgumentException("Uploaded file is not a valid Excel file (.xlsx or .xls): " + e.getMessage(), e);
        }
    }

    private List<CompanyProposalOverviewDto> getOverviewsForCompany(String company, String proposalTypeFilter) {
        String rootPath = normalizePath(properties.basePath());
        String resolvedCompany = resolveDirectoryName(rootPath, company);
        if (resolvedCompany == null) {
            throw new EntityNotFoundException("Company directory '" + company + "' does not exist at " + rootPath);
        }

        String companyPath = rootPath + "/" + resolvedCompany;
        List<String> versions = listVersions(companyPath);
        if (versions.isEmpty()) {
            throw new EntityNotFoundException("No proposal versions found for company '" + resolvedCompany + "'");
        }

        List<CompanyProposalOverviewDto> overviews = findLatestProposalsForCompany(rootPath, resolvedCompany, versions, proposalTypeFilter);
        if (overviews.isEmpty()) {
            String latestVersion = versions.get(versions.size() - 1);
            String versionPath = companyPath + "/" + latestVersion;
            SftpClient.DirEntry[] versionEntries = listVersionEntries(versionPath);
            CompanyProposalOverviewDto fallback = buildCompanyOverviewFallback(resolvedCompany, latestVersion, versionPath, versionEntries, proposalTypeFilter);
            if (fallback != null) {
                return List.of(fallback);
            }
            throw new EntityNotFoundException("No proposal versions found for company '" + resolvedCompany + "'");
        }
        return overviews;
    }

    private List<CompanyProposalOverviewDto> listAllProposals(String proposalTypeFilter) {
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

            String companyPath = rootPath + "/" + entryName;
            List<String> versions = listVersions(companyPath);
            List<CompanyProposalOverviewDto> companyOverviews = findLatestProposalsForCompany(rootPath, entryName, versions, proposalTypeFilter);
            results.addAll(companyOverviews);
        }

        // Newest upload first; the company name keeps the order stable
        results.sort(Comparator
                .comparing((CompanyProposalOverviewDto p) -> parseUploadTime(p.createdDate()),
                        Comparator.nullsLast(Comparator.reverseOrder()))
                .thenComparing(CompanyProposalOverviewDto::company, String.CASE_INSENSITIVE_ORDER));
        return results;
    }

    private List<CompanyProposalOverviewDto> findLatestProposalsForCompany(
            String rootPath, String companyName, List<String> versions, String proposalTypeFilter) {
        String companyPath = rootPath + "/" + companyName;
        Map<String, CompanyProposalOverviewDto> latestByType = new LinkedHashMap<>();

        for (int i = versions.size() - 1; i >= 0; i--) {
            String version = versions.get(i);
            String versionPath = companyPath + "/" + version;
            SftpClient.DirEntry[] versionEntries = listVersionEntries(versionPath);

            List<SftpClient.DirEntry> subdirs = new ArrayList<>();
            for (SftpClient.DirEntry entry : versionEntries) {
                if (!isSpecialDirectory(entry.getFilename()) && isDirectory(entry)) {
                    subdirs.add(entry);
                }
            }

            if (!subdirs.isEmpty()) {
                for (SftpClient.DirEntry subdir : subdirs) {
                    String typeName = subdir.getFilename();
                    if (proposalTypeFilter != null && !typeName.equalsIgnoreCase(proposalTypeFilter)) {
                        continue;
                    }
                    String typeKey = typeName.toLowerCase();
                    if (latestByType.containsKey(typeKey)) {
                        continue;
                    }
                    String typePath = versionPath + "/" + typeName;
                    SftpClient.DirEntry[] typeEntries = listVersionEntries(typePath);
                    ProposalMetadata metadata = readMetadata(typePath, typeEntries);
                    if (metadata == null || metadata.status() == null) {
                        continue;
                    }
                    String problem = findMetadataProblem(metadata);
                    if (problem != null) {
                        log.warn("Skipping proposal {}: {}", typePath, problem);
                        continue;
                    }
                    CompanyProposalOverviewDto dto = toOverview(companyName, version, typePath, typeName.toLowerCase(), typeEntries, metadata);
                    latestByType.put(typeKey, dto);
                }
            } else {
                ProposalMetadata metadata = readMetadata(versionPath, versionEntries);
                if (metadata == null || metadata.status() == null) {
                    continue;
                }
                String problem = findMetadataProblem(metadata);
                if (problem != null) {
                    log.warn("Skipping proposal {}: {}", versionPath, problem);
                    continue;
                }
                String typeName = metadata.proposalType() != null ? metadata.proposalType().toLowerCase() : "";
                if (proposalTypeFilter != null && !proposalTypeFilter.equalsIgnoreCase(typeName)) {
                    continue;
                }
                String typeKey = typeName.toLowerCase();
                if (!latestByType.containsKey(typeKey)) {
                    CompanyProposalOverviewDto dto = toOverview(companyName, version, versionPath, typeName.toLowerCase(), versionEntries, metadata);
                    latestByType.put(typeKey, dto);
                }
            }

            if (!latestByType.isEmpty()) {
                break;
            }
        }

        return new ArrayList<>(latestByType.values());
    }

    private CompanyProposalOverviewDto buildCompanyOverviewFallback(
            String companyName, String version, String versionPath, SftpClient.DirEntry[] versionEntries, String proposalTypeFilter) {
        for (SftpClient.DirEntry entry : versionEntries) {
            if (!isSpecialDirectory(entry.getFilename()) && isDirectory(entry)) {
                String typeName = entry.getFilename().toLowerCase();
                if (proposalTypeFilter != null && !typeName.equalsIgnoreCase(proposalTypeFilter)) {
                    continue;
                }
                String typePath = versionPath + "/" + entry.getFilename();
                SftpClient.DirEntry[] typeEntries = listVersionEntries(typePath);
                ProposalMetadata metadata = readMetadata(typePath, typeEntries);
                return toOverview(companyName, version, typePath, typeName, typeEntries, metadata);
            }
        }
        ProposalMetadata metadata = readMetadata(versionPath, versionEntries);
        String typeName = metadata != null && metadata.proposalType() != null ? metadata.proposalType().toLowerCase() : null;
        if (proposalTypeFilter != null && (typeName == null || !typeName.equalsIgnoreCase(proposalTypeFilter))) {
            return null;
        }
        return toOverview(companyName, version, versionPath, typeName, versionEntries, metadata);
    }

    // Version folders of a company, sorted from oldest to newest (v2 before v10)
    private List<String> listVersions(String companyPath) {
        SftpClient.DirEntry[] companyEntries = template.list(companyPath);
        List<String> versions = new ArrayList<>();
        if (companyEntries == null) {
            return versions;
        }

        for (SftpClient.DirEntry entry : companyEntries) {
            String name = entry.getFilename();
            if (!isSpecialDirectory(name) && isDirectory(entry)) {
                versions.add(name);
            }
        }
        versions.sort(VersionComparator.INSTANCE);
        return versions;
    }

    private SftpClient.DirEntry[] listVersionEntries(String versionPath) {
        SftpClient.DirEntry[] versionEntries = template.list(versionPath);
        return versionEntries != null ? versionEntries : new SftpClient.DirEntry[0];
    }

    // Returns why the proposal data cannot be shown in the overview, or null when it is valid
    private String findMetadataProblem(ProposalMetadata metadata) {
        if (metadata == null) {
            return "metadata.json / proposal.json is missing or not valid JSON";
        }
        if (metadata.status() == null || !PROPOSAL_STATUSES.contains(metadata.status())) {
            return "unknown status '" + metadata.status() + "'";
        }
        if (metadata.aiStatus() != null && !metadata.aiStatus().isBlank() && !AI_STATUSES.contains(metadata.aiStatus())) {
            return "unknown AI status '" + metadata.aiStatus() + "'";
        }
        if (parseUploadTime(metadata.createdDate()) == null) {
            return "upload time is missing or not an ISO 8601 timestamp";
        }
        return null;
    }

    // ISO 8601 upload time, e.g. 2026-10-22T14:05:00+02:00; a time without timezone is taken as UTC
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

    static String[] parseDateAndTime(String timestamp) {
        if (timestamp == null || timestamp.isBlank()) {
            return new String[]{null, null};
        }
        String text = timestamp.trim();
        try {
            OffsetDateTime odt = OffsetDateTime.parse(text);
            String date = odt.toLocalDate().toString();
            String time = odt.toLocalTime().format(DateTimeFormatter.ofPattern("HH:mm:ss"));
            return new String[]{date, time};
        } catch (DateTimeParseException ignored) {
        }
        try {
            LocalDateTime ldt = LocalDateTime.parse(text);
            String date = ldt.toLocalDate().toString();
            String time = ldt.toLocalTime().format(DateTimeFormatter.ofPattern("HH:mm:ss"));
            return new String[]{date, time};
        } catch (DateTimeParseException ignored) {
        }
        try {
            Instant instant = Instant.parse(text);
            OffsetDateTime odt = instant.atOffset(ZoneOffset.UTC);
            String date = odt.toLocalDate().toString();
            String time = odt.toLocalTime().format(DateTimeFormatter.ofPattern("HH:mm:ss"));
            return new String[]{date, time};
        } catch (DateTimeParseException ignored) {
        }
        if (text.contains("T")) {
            String[] parts = text.split("T", 2);
            String date = parts[0].trim();
            String timePart = parts[1].trim();
            String time = timePart.replaceAll("([+-]\\d{2}:?\\d{2}|Z)$", "").trim();
            if (time.length() > 8) {
                time = time.substring(0, 8);
            }
            return new String[]{date, time.isBlank() ? null : time};
        }
        if (text.contains(" ")) {
            String[] parts = text.split(" ", 2);
            return new String[]{parts[0].trim(), parts[1].trim()};
        }
        return new String[]{text, null};
    }

    private CompanyProposalOverviewDto toOverview(String companyName, String version, String versionPath,
                                                  String proposalType, SftpClient.DirEntry[] versionEntries,
                                                  ProposalMetadata metadata) {
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
        String customerName = (metadata != null) ? metadata.company() : null;
        String finalProposalType = (proposalType != null && !proposalType.isBlank())
                ? proposalType.toLowerCase()
                : (metadata != null && metadata.proposalType() != null ? metadata.proposalType().toLowerCase() : null);

        return new CompanyProposalOverviewDto(
                companyName,
                version,
                filename,
                fullPath,
                createdDate,
                createdBy,
                description,
                status,
                aiStatus,
                customerName,
                finalProposalType
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

    private String extractFileModifyTimestamp(SftpClient.DirEntry entry) {
        if (entry == null || entry.getAttributes() == null) {
            return null;
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

    private void validateCompany(String company) {
        if (company == null || company.isBlank()) {
            throw new IllegalArgumentException("Company parameter must not be empty");
        }
        if (company.length() > MAX_COMPANY_LENGTH) {
            throw new IllegalArgumentException("Company parameter must not exceed " + MAX_COMPANY_LENGTH + " characters");
        }
    }

    private void validateVersion(String version) {
        if (version == null || version.isBlank()) {
            throw new IllegalArgumentException("Version parameter must not be empty");
        }
    }

    private void validateProposalTypeIfPresent(String proposalType) {
        if (proposalType != null) {
            if (proposalType.isBlank()) {
                throw new IllegalArgumentException("Proposal type parameter must not be empty");
            }
            if (proposalType.length() > MAX_PROPOSAL_TYPE_LENGTH) {
                throw new IllegalArgumentException("Proposal type parameter must not exceed " + MAX_PROPOSAL_TYPE_LENGTH + " characters");
            }
        }
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
