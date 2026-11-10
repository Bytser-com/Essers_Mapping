package be.essers.services.versioncontrol.domain.proposal.service;

import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDto;
import be.essers.services.versioncontrol.infrastructure.sftp.SftpProperties;
import be.essers.services.versioncontrol.shared.exception.EntityNotFoundException;
import be.essers.services.versioncontrol.shared.exception.StorageException;
import org.apache.sshd.sftp.client.SftpClient;
import org.apache.sshd.sftp.common.SftpConstants;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@Service
public class SftpProposalStorageService implements ProposalStorageService {

    private static final Logger log = LoggerFactory.getLogger(SftpProposalStorageService.class);

    private final SftpRemoteFileTemplate template;
    private final SftpProperties properties;

    public SftpProposalStorageService(SftpRemoteFileTemplate template, SftpProperties properties) {
        this.template = template;
        this.properties = properties;
    }

    @Override
    public List<ProposalFileDto> listProposals(String company) {
        try {
            if (company != null && !company.isBlank()) {
                return listProposalsForCompany(sanitizeCompanyName(company));
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
    public List<String> listProposalFilenames(String company) {
        return listProposals(company).stream()
                .map(ProposalFileDto::filename)
                .toList();
    }

    private List<ProposalFileDto> listProposalsForCompany(String company) {
        String companyPath = normalizePath(properties.basePath()) + "/" + company;
        if (!template.exists(companyPath)) {
            throw new EntityNotFoundException("Company directory '" + company + "' does not exist at " + companyPath);
        }

        SftpClient.DirEntry[] entries = template.list(companyPath);
        if (entries == null || entries.length == 0) {
            return Collections.emptyList();
        }

        List<ProposalFileDto> results = new ArrayList<>();
        for (SftpClient.DirEntry entry : entries) {
            String filename = entry.getFilename();
            if (isSpecialDirectory(filename) || isDirectory(entry)) {
                continue;
            }
            results.add(new ProposalFileDto(company, filename, companyPath + "/" + filename));
        }
        return results;
    }

    private List<ProposalFileDto> listAllProposals() {
        String rootPath = normalizePath(properties.basePath());
        if (!template.exists(rootPath)) {
            log.warn("Root proposals directory '{}' does not exist on SFTP server", rootPath);
            return Collections.emptyList();
        }

        SftpClient.DirEntry[] entries = template.list(rootPath);
        if (entries == null || entries.length == 0) {
            return Collections.emptyList();
        }

        List<ProposalFileDto> results = new ArrayList<>();
        for (SftpClient.DirEntry entry : entries) {
            String entryName = entry.getFilename();
            if (isSpecialDirectory(entryName)) {
                continue;
            }

            if (isDirectory(entry)) {
                String companyName = entryName;
                String companyPath = rootPath + "/" + companyName;
                SftpClient.DirEntry[] companyFiles = template.list(companyPath);
                if (companyFiles != null) {
                    for (SftpClient.DirEntry fileEntry : companyFiles) {
                        String filename = fileEntry.getFilename();
                        if (isSpecialDirectory(filename) || isDirectory(fileEntry)) {
                            continue;
                        }
                        results.add(new ProposalFileDto(companyName, filename, companyPath + "/" + filename));
                    }
                }
            }
        }
        return results;
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

    private String sanitizeCompanyName(String company) {
        String trimmed = company.trim();
        if (trimmed.contains("/") || trimmed.contains("\\") || trimmed.contains("..")) {
            throw new IllegalArgumentException("Company name contains illegal path traversal characters: " + company);
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
