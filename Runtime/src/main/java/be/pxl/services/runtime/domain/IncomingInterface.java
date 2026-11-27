package be.pxl.services.runtime.domain;

import java.time.Instant;
import java.util.Objects;

/**
 * Metadata of an unclaimed customer XML interface discovered in {@code incoming/}.
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
        customer = requireNonBlank(customer, "customer");
        messageType = requireNonBlank(messageType, "messageType");
        filename = requireNonBlank(filename, "filename");
        baseDir = requireNonBlank(baseDir, "baseDir");
        remotePath = requireNonBlank(remotePath, "remotePath");
        Objects.requireNonNull(lastModified, "lastModified must not be null");
    }

    private static String requireNonBlank(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value.trim();
    }
}
