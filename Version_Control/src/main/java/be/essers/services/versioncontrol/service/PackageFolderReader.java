package be.essers.services.versioncontrol.service;

import be.essers.services.versioncontrol.domain.dto.MappingPackage;
import org.apache.sshd.sftp.client.SftpClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;
import tools.jackson.databind.ObjectMapper;

import java.io.ByteArrayOutputStream;
import java.util.List;

/** Reads a package type folder and the {@code meta} block of its MPackage.json from SFTP. */
final class PackageFolderReader {

    private static final Logger log = LoggerFactory.getLogger(PackageFolderReader.class);

    private final SftpRemoteFileTemplate template;
    private final SftpFolders folders;
    private final ObjectMapper objectMapper;

    PackageFolderReader(SftpRemoteFileTemplate template, SftpFolders folders, ObjectMapper objectMapper) {
        this.template = template;
        this.folders = folders;
        this.objectMapper = objectMapper;
    }

    PackageFolder read(String versionPath, String typeName) {
        String typePath = SftpFolders.path(versionPath, typeName);
        List<SftpClient.DirEntry> entries = List.of(folders.list(typePath));
        return new PackageFolder(typeName, entries, readMetadata(typePath, entries));
    }

    private MappingPackage.Meta readMetadata(String typePath, List<SftpClient.DirEntry> entries) {
        String filename = findMetadataFilename(entries);
        if (filename == null) {
            return null;
        }
        String path = SftpFolders.path(typePath, filename);
        try {
            ByteArrayOutputStream content = new ByteArrayOutputStream();
            boolean found = template.get(path, in -> in.transferTo(content));
            if (!found || content.size() == 0) {
                return null;
            }
            MappingPackage mappingPackage = objectMapper.readValue(content.toByteArray(), MappingPackage.class);
            return mappingPackage != null ? mappingPackage.meta() : null;
        } catch (Exception e) {
            log.warn("Failed to parse metadata file at {}: {}", path, e.getMessage());
            return null;
        }
    }

    // Actual filename of MPackage.json in the folder (case-insensitive match), or null
    private static String findMetadataFilename(List<SftpClient.DirEntry> entries) {
        for (SftpClient.DirEntry entry : entries) {
            if (PackageFolder.METADATA_FILENAME.equalsIgnoreCase(entry.getFilename()) && !SftpFolders.isDirectory(entry)) {
                return entry.getFilename();
            }
        }
        return null;
    }
}
