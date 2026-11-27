package be.pxl.services.runtime.storage;

import java.nio.file.NoSuchFileException;
import java.nio.file.attribute.FileTime;
import java.time.Instant;
import java.util.Locale;
import java.util.Optional;
import java.util.UUID;

import org.apache.sshd.sftp.client.SftpClient;
import org.apache.sshd.sftp.common.SftpConstants;
import org.apache.sshd.sftp.common.SftpException;

import be.pxl.services.runtime.config.RuntimePollerProperties;
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

    static String shortToken() {
        return UUID.randomUUID().toString().substring(0, 8);
    }

    /**
     * Format: {@code <filename>.<claimedEpochMs>.<safeInstanceId>.<token>.processing}.
     * Embedding {@code claimedEpochMs} ensures stale-claim recovery is immune to POSIX
     * {@code rename} preserving the original upload {@code mtime}.
     */
    static String buildClaimedFilename(String filename, String instanceId, Instant claimedAt) {
        String safeInstance = requireSafeInstanceId(instanceId);
        return filename + "." + claimedAt.toEpochMilli() + "." + safeInstance + "." + shortToken() + PROCESSING_SUFFIX;
    }

    static String buildCollisionFreeName(String filename, long epochMillis, String token) {
        String suffix = "_" + epochMillis + "_" + token;
        int dotIndex = filename.lastIndexOf('.');
        return dotIndex > 0
                ? filename.substring(0, dotIndex) + suffix + filename.substring(dotIndex)
                : filename + suffix;
    }

    static String extractOriginalFilename(String claimedFilename) {
        String body = stripProcessingSuffix(claimedFilename);
        int tokenDot = body.lastIndexOf('.');
        int instanceDot = tokenDot > 0 ? body.lastIndexOf('.', tokenDot - 1) : -1;
        if (instanceDot > 0) {
            int timestampDot = body.lastIndexOf('.', instanceDot - 1);
            if (timestampDot > 0 && parsePositiveEpochMillis(body.substring(timestampDot + 1, instanceDot)).isPresent()) {
                return body.substring(0, timestampDot);
            }
            return body.substring(0, instanceDot);
        }
        return body;
    }

    static Optional<Instant> extractClaimTimestamp(SftpClient.DirEntry entry) {
        if (entry == null || entry.getFilename() == null) {
            return Optional.empty();
        }
        String body = stripProcessingSuffix(entry.getFilename());
        int tokenDot = body.lastIndexOf('.');
        int instanceDot = tokenDot > 0 ? body.lastIndexOf('.', tokenDot - 1) : -1;
        int timestampDot = instanceDot > 0 ? body.lastIndexOf('.', instanceDot - 1) : -1;
        if (timestampDot > 0) {
            Optional<Long> epochMs = parsePositiveEpochMillis(body.substring(timestampDot + 1, instanceDot));
            if (epochMs.isPresent()) {
                return Optional.of(Instant.ofEpochMilli(epochMs.get()));
            }
        }
        return extractModifyTime(entry);
    }

    static String buildErrorNote(ClaimedInterface claimed, String reason, Instant timestamp) {
        String safeReason = sanitizeSingleLine(reason);
        if (safeReason.isEmpty()) {
            safeReason = "Unknown processing error";
        }
        return "timestamp=" + timestamp + System.lineSeparator()
                + "customer=" + sanitizeSingleLine(claimed.customer()) + System.lineSeparator()
                + "messageType=" + sanitizeSingleLine(claimed.messageType()) + System.lineSeparator()
                + "filename=" + sanitizeSingleLine(claimed.filename()) + System.lineSeparator()
                + "reason=" + safeReason + System.lineSeparator();
    }

    static boolean isEligibleXmlFile(SftpClient.DirEntry entry, Instant cutoff) {
        if (!isRegularFile(entry)) {
            return false;
        }
        String filename = entry.getFilename();
        if (!isSafeSegment(filename) || !filename.toLowerCase(Locale.ROOT).endsWith(XML_EXTENSION)) {
            return false;
        }
        return extractModifyTime(entry).map(modified -> !modified.isAfter(cutoff)).orElse(false);
    }

    static boolean isStaleProcessingFile(SftpClient.DirEntry entry, Instant staleCutoff) {
        if (!isRegularFile(entry)) {
            return false;
        }
        String filename = entry.getFilename();
        if (!isSafeSegment(filename) || !filename.endsWith(PROCESSING_SUFFIX)) {
            return false;
        }
        return extractClaimTimestamp(entry).map(claimedAt -> !claimedAt.isAfter(staleCutoff)).orElse(false);
    }

    static boolean isSafeSegment(String segment) {
        if (segment == null || segment.isBlank() || segment.startsWith(".")) {
            return false;
        }
        for (int i = 0; i < segment.length(); i++) {
            char ch = segment.charAt(i);
            if (ch == '/' || ch == '\\' || ch < 0x20 || ch == 0x7F) {
                return false;
            }
        }
        return true;
    }

    static boolean isDirectory(SftpClient.DirEntry entry) {
        if (entry == null || entry.getAttributes() == null) {
            return false;
        }
        SftpClient.Attributes attrs = entry.getAttributes();
        return !attrs.isSymbolicLink()
                && (attrs.isDirectory() || attrs.getType() == SftpConstants.SSH_FILEXFER_TYPE_DIRECTORY);
    }

    static boolean isRegularFile(SftpClient.DirEntry entry) {
        if (entry == null || entry.getAttributes() == null) {
            return false;
        }
        SftpClient.Attributes attrs = entry.getAttributes();
        return !attrs.isSymbolicLink() && !isDirectory(entry);
    }

    static Optional<Instant> extractModifyTime(SftpClient.DirEntry entry) {
        if (entry != null && entry.getAttributes() != null) {
            FileTime modifyTime = entry.getAttributes().getModifyTime();
            if (modifyTime != null) {
                return Optional.of(modifyTime.toInstant());
            }
        }
        return Optional.empty();
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

    static String sanitizeSingleLine(String raw) {
        if (raw == null) {
            return "";
        }
        StringBuilder sb = new StringBuilder(raw.length());
        for (int i = 0; i < raw.length(); i++) {
            char ch = raw.charAt(i);
            if (ch == '\r' || ch == '\n' || ch == '\t') {
                sb.append(' ');
            } else if (ch >= 0x20 && ch != 0x7F) {
                sb.append(ch);
            }
        }
        return sb.toString().trim();
    }

    private static String stripProcessingSuffix(String claimedFilename) {
        return claimedFilename.endsWith(PROCESSING_SUFFIX)
                ? claimedFilename.substring(0, claimedFilename.length() - PROCESSING_SUFFIX.length())
                : claimedFilename;
    }

    private static Optional<Long> parsePositiveEpochMillis(String candidate) {
        if (candidate == null || candidate.isEmpty()) {
            return Optional.empty();
        }
        for (int i = 0; i < candidate.length(); i++) {
            if (!Character.isDigit(candidate.charAt(i))) {
                return Optional.empty();
            }
        }
        try {
            long value = Long.parseLong(candidate);
            return value > 0 ? Optional.of(value) : Optional.empty();
        } catch (NumberFormatException ex) {
            return Optional.empty();
        }
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

    private static String requireSafeInstanceId(String instanceId) {
        String cleaned = RuntimePollerProperties.cleanInstanceId(instanceId);
        if (cleaned.isEmpty()) {
            throw new IllegalArgumentException("instanceId must not be blank");
        }
        return cleaned;
    }
}
