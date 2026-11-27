package be.essers.services.versioncontrol.service;

import org.apache.sshd.sftp.client.SftpClient;
import org.apache.sshd.sftp.common.SftpConstants;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;

import java.util.ArrayList;
import java.util.List;

/**
 * Folders on the SFTP server: building paths, listing folders and finding a folder
 * case-insensitively. Keeps the path handling of the storage services in one place.
 */
final class SftpFolders {

    static final String SEPARATOR = "/";

    private final SftpRemoteFileTemplate template;

    SftpFolders(SftpRemoteFileTemplate template) {
        this.template = template;
    }

    /** Joins path segments with the SFTP separator: {@code path("/Packages", "nouryon", "v1")}. */
    static String path(String first, String... more) {
        StringBuilder result = new StringBuilder(first);
        for (String segment : more) {
            result.append(SEPARATOR).append(segment);
        }
        return result.toString();
    }

    /** One folder or file name from user input, trimmed; rejects anything that could leave the folder. */
    static String sanitizeSegment(String segment) {
        String trimmed = segment.trim();
        if (trimmed.contains(SEPARATOR) || trimmed.contains("\\") || trimmed.contains("..")) {
            throw new IllegalArgumentException("Path segment contains illegal characters: " + segment);
        }
        return trimmed;
    }

    static boolean isDirectory(SftpClient.DirEntry entry) {
        if (entry.getAttributes() == null) {
            return false;
        }
        return entry.getAttributes().isDirectory()
                || entry.getAttributes().getType() == SftpConstants.SSH_FILEXFER_TYPE_DIRECTORY;
    }

    boolean exists(String path) {
        return template.exists(path);
    }

    /** Entries of a folder; empty when the folder is missing. */
    SftpClient.DirEntry[] list(String path) {
        SftpClient.DirEntry[] entries = template.list(path);
        return entries != null ? entries : new SftpClient.DirEntry[0];
    }

    /** Names of the subfolders of a folder, without "." and "..". */
    List<String> subfolders(String path) {
        List<String> names = new ArrayList<>();
        for (SftpClient.DirEntry entry : list(path)) {
            if (!isSpecial(entry.getFilename()) && isDirectory(entry)) {
                names.add(entry.getFilename());
            }
        }
        return names;
    }

    /**
     * Actual name of the subfolder {@code name} of {@code parentPath}: the exact name when it exists,
     * otherwise a case-insensitive match, or null when there is none.
     */
    String findSubfolder(String parentPath, String name) {
        if (template.exists(path(parentPath, name))) {
            return name;
        }
        for (String folder : subfolders(parentPath)) {
            if (folder.equalsIgnoreCase(name)) {
                return folder;
            }
        }
        return null;
    }

    private static boolean isSpecial(String name) {
        return ".".equals(name) || "..".equals(name);
    }
}
