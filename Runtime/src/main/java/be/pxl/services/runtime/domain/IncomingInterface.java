package be.pxl.services.runtime.domain;

import java.time.Instant;
import java.util.Objects;

/**
 * Metadata of an unclaimed customer XML interface discovered in {@code incoming/}.
 * SFTP names and paths are preserved verbatim without trimming so they always match remote paths.
 */
public record IncomingInterface(
        String customer,
        String messageType,
        String filename,
        String baseDir,
        String remotePath,
        Instant lastModified
) {
    public IncomingInterface {
        customer = requireExactNonBlank(customer, "customer");
        messageType = requireExactNonBlank(messageType, "messageType");
        filename = requireExactNonBlank(filename, "filename");
        baseDir = requireExactNonBlank(baseDir, "baseDir");
        remotePath = requireExactNonBlank(remotePath, "remotePath");
        Objects.requireNonNull(lastModified, "lastModified must not be null");
    }

    private static String requireExactNonBlank(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        if (!value.equals(value.trim())) {
            throw new IllegalArgumentException(field + " must not have leading or trailing whitespace");
        }
        return value;
    }
}
