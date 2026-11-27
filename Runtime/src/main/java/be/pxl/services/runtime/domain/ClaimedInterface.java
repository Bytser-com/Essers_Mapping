package be.pxl.services.runtime.domain;

/**
 * Reference to a customer XML interface exclusively claimed by a single runtime pod
 * via atomic rename into {@code processing/}.
 * SFTP names and paths are preserved verbatim without trimming.
 */
public record ClaimedInterface(
        String customer,
        String messageType,
        String filename,
        String baseDir,
        String claimedPath
) {
    public ClaimedInterface {
        customer = requireExactNonBlank(customer, "customer");
        messageType = requireExactNonBlank(messageType, "messageType");
        filename = requireExactNonBlank(filename, "filename");
        baseDir = requireExactNonBlank(baseDir, "baseDir");
        claimedPath = requireExactNonBlank(claimedPath, "claimedPath");
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
