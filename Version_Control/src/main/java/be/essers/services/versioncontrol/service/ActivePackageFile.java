package be.essers.services.versioncontrol.service;

import be.essers.services.versioncontrol.domain.dto.ActivePackageInfo;
import be.essers.services.versioncontrol.exception.StorageException;
import org.apache.sshd.sftp.client.SftpClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.file.remote.session.Session;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

/**
 * The active version per package type of one company:
 * {@code <sftp.packages-path>/<company>/active.json}, e.g.
 * {@code {"inbound": {"version": "v2", "updated_at": "...", "updated_by": "..."}}}.
 * An older layout with the types inside a {@code "types"} block is still read.
 */
final class ActivePackageFile {

    static final String FILENAME = "active.json";

    private static final Logger log = LoggerFactory.getLogger(ActivePackageFile.class);
    private static final String TYPES_BLOCK = "types";

    private final SftpRemoteFileTemplate template;
    private final SftpFolders folders;
    private final ObjectMapper objectMapper;

    ActivePackageFile(SftpRemoteFileTemplate template, SftpFolders folders, ObjectMapper objectMapper) {
        this.template = template;
        this.folders = folders;
        this.objectMapper = objectMapper;
    }

    /**
     * Active version per package type (lowercase). Empty when the file is missing or unreadable:
     * the overview then falls back to the newest version.
     */
    Map<String, ActivePackageInfo> read(String companyPath) {
        String path = SftpFolders.path(companyPath, FILENAME);
        if (!folders.exists(path)) {
            return new HashMap<>();
        }
        try {
            byte[] content = download(path);
            return content.length == 0 ? new HashMap<>() : parse(content);
        } catch (Exception e) {
            log.warn("Failed to read active.json at {}: {}", path, e.getMessage());
            return new HashMap<>();
        }
    }

    /**
     * Writes the file via a temporary file and a rename, so a reader never sees a half-written file.
     * Throws StorageException when it cannot be written.
     */
    void write(String companyPath, Map<String, ActivePackageInfo> activeByType) {
        String path = SftpFolders.path(companyPath, FILENAME);
        String tempPath = SftpFolders.path(companyPath, "." + FILENAME + ".tmp");
        try {
            byte[] content = objectMapper.writerWithDefaultPrettyPrinter().writeValueAsBytes(activeByType);
            template.execute(session -> {
                session.write(new ByteArrayInputStream(content), tempPath);
                replace(session, tempPath, path);
                return null;
            });
        } catch (Exception e) {
            log.error("Failed to write active.json at {}: {}", path, e.getMessage(), e);
            throw new StorageException("Unable to update active.json: " + e.getMessage(), e);
        }
    }

    private byte[] download(String path) {
        ByteArrayOutputStream content = new ByteArrayOutputStream();
        boolean found = template.get(path, in -> in.transferTo(content));
        return found ? content.toByteArray() : new byte[0];
    }

    private Map<String, ActivePackageInfo> parse(byte[] content) {
        Map<String, ActivePackageInfo> result = new HashMap<>();
        JsonNode root = objectMapper.readTree(content);
        if (root == null || !root.isObject()) {
            return result;
        }
        JsonNode types = root.path(TYPES_BLOCK).isObject() ? root.get(TYPES_BLOCK) : root;
        for (var entry : types.properties()) {
            ActivePackageInfo info = objectMapper.treeToValue(entry.getValue(), ActivePackageInfo.class);
            if (info != null && info.version() != null && !info.version().isBlank()) {
                result.put(entry.getKey().toLowerCase(), info);
            }
        }
        return result;
    }

    // Some SFTP servers do not overwrite an existing file on rename: then remove it and rename again.
    private static void replace(Session<SftpClient.DirEntry> session, String from, String to) throws IOException {
        try {
            session.rename(from, to);
        } catch (IOException renameFailed) {
            removeIfPresent(session, to);
            session.rename(from, to);
        }
    }

    // A missing file is fine here: the second rename then simply creates it.
    private static void removeIfPresent(Session<SftpClient.DirEntry> session, String path) {
        try {
            session.remove(path);
        } catch (IOException e) {
            log.debug("Could not remove {} before renaming: {}", path, e.getMessage());
        }
    }
}
