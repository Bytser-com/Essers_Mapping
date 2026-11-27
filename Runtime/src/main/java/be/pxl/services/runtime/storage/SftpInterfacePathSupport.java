package be.pxl.services.runtime.storage;

import java.nio.file.NoSuchFileException;
import java.nio.file.attribute.FileTime;
import java.time.Instant;
import java.util.Locale;
import java.util.UUID;

import org.apache.sshd.sftp.client.SftpClient;
import org.apache.sshd.sftp.common.SftpConstants;
import org.apache.sshd.sftp.common.SftpException;

import be.pxl.services.runtime.domain.ClaimedInterface;

/**
 * Pure path, filename, filtering, and SFTP error-classification helpers for
 * {@link SftpRuntimeInterfaceStorage}.
 */
final class SftpInterfacePathSupport {

    static final String INCOMING_DIR = "incoming";
    static final String PROCESSING_DIR = "processing";
    static final String PROCESSED_DIR = "processed";
    static final String ERROR_DIR = "error";
    static final String PROCESSING_SUFFIX = ".processing";
    static final String ERROR_NOTE_SUFFIX = ".error.txt";
    private static final String XML_EXTENSION = ".xml";

    private SftpInterfacePathSupport() {
    }

    static String normalizeRoot(String root) {
        if (root == null || root.isBlank() || "/".equals(root.trim())) {
            return "/";
        }
        String trimmed = root.trim();
        while (trimmed.endsWith("/") && trimmed.length() > 1) {
            trimmed = trimmed.substring(0, trimmed.length() - 1);
        }
        return trimmed;
    }

    static String joinPath(String parent, String child) {
        return "/".equals(parent) ? "/" + child : parent + "/" + child;
    }

    static String buildClaimedFilename(String filename, String instanceId) {
        String safeInstance = sanitizeInstanceId(instanceId);
        String claimToken = UUID.randomUUID().toString().substring(0, 8);
        return filename + "." + safeInstance + "." + claimToken + PROCESSING_SUFFIX;
    }

    static String buildCollisionFreeName(String filename, long epochMillis) {
        String suffix = "_" + epochMillis;
        int dotIndex = filename.lastIndexOf('.');
        return dotIndex > 0
                ? filename.substring(0, dotIndex) + suffix + filename.substring(dotIndex)
                : filename + suffix;
    }

    static String extractOriginalFilename(String claimedFilename) {
        String withoutSuffix = claimedFilename.endsWith(PROCESSING_SUFFIX)
                ? claimedFilename.substring(0, claimedFilename.length() - PROCESSING_SUFFIX.length())
                : claimedFilename;
        int xmlEnd = withoutSuffix.toLowerCase(Locale.ROOT).lastIndexOf(XML_EXTENSION);
        return xmlEnd > 0 ? withoutSuffix.substring(0, xmlEnd + XML_EXTENSION.length()) : withoutSuffix;
    }

    static String buildErrorNote(ClaimedInterface claimed, String reason, Instant timestamp) {
        String safeReason = (reason == null || reason.isBlank()) ? "Unknown processing error" : reason.trim();
        return "timestamp=" + timestamp + System.lineSeparator()
                + "customer=" + claimed.customer() + System.lineSeparator()
                + "messageType=" + claimed.messageType() + System.lineSeparator()
                + "filename=" + claimed.filename() + System.lineSeparator()
                + "reason=" + safeReason + System.lineSeparator();
    }

    static boolean isEligibleXmlFile(SftpClient.DirEntry entry, Instant cutoff) {
        if (isDirectory(entry)) {
            return false;
        }
        String filename = entry.getFilename();
        return isSafeSegment(filename)
                && filename.toLowerCase(Locale.ROOT).endsWith(XML_EXTENSION)
                && !extractModifyTime(entry).isAfter(cutoff);
    }

    static boolean isStaleProcessingFile(SftpClient.DirEntry entry, Instant staleCutoff) {
        if (isDirectory(entry)) {
            return false;
        }
        String filename = entry.getFilename();
        return isSafeSegment(filename)
                && filename.endsWith(PROCESSING_SUFFIX)
                && !extractModifyTime(entry).isAfter(staleCutoff);
    }

    static boolean isSafeSegment(String segment) {
        return segment != null
                && !segment.isBlank()
                && !".".equals(segment)
                && !"..".equals(segment)
                && !segment.contains("/")
                && !segment.contains("\\")
                && !segment.contains("..");
    }

    static boolean isDirectory(SftpClient.DirEntry entry) {
        if (entry == null || entry.getAttributes() == null) {
            return false;
        }
        return entry.getAttributes().isDirectory()
                || entry.getAttributes().getType() == SftpConstants.SSH_FILEXFER_TYPE_DIRECTORY;
    }

    static Instant extractModifyTime(SftpClient.DirEntry entry) {
        if (entry != null && entry.getAttributes() != null) {
            FileTime modifyTime = entry.getAttributes().getModifyTime();
            if (modifyTime != null) {
                return modifyTime.toInstant();
            }
        }
        return Instant.EPOCH;
    }

    static boolean isMissingFileError(Throwable error) {
        Throwable current = error;
        while (current != null) {
            if (isDirectMissingCause(current)) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private static boolean isDirectMissingCause(Throwable cause) {
        if (cause instanceof NoSuchFileException) {
            return true;
        }
        if (cause instanceof SftpException sftpEx
                && sftpEx.getStatus() == SftpConstants.SSH_FX_NO_SUCH_FILE) {
            return true;
        }
        String message = cause.getMessage();
        return message != null && message.toLowerCase(Locale.ROOT).contains("no such file");
    }

    private static String sanitizeInstanceId(String instanceId) {
        String cleaned = instanceId == null ? "" : instanceId.trim().replaceAll("[^A-Za-z0-9._-]", "");
        if (cleaned.isEmpty()) {
            throw new IllegalArgumentException("instanceId must not be blank");
        }
        return cleaned;
    }
}
