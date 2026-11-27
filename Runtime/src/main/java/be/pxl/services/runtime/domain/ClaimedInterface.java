package be.pxl.services.runtime.domain;

/**
 * Reference to a customer XML interface exclusively claimed by a single runtime pod
 * via atomic rename into {@code processing/}.
 */
public record ClaimedInterface(
        String customer,
        String messageType,
        String filename,
        String baseDir,
        String claimedPath
) {
    public ClaimedInterface {
        customer = requireNonBlank(customer, "customer");
        messageType = requireNonBlank(messageType, "messageType");
        filename = requireNonBlank(filename, "filename");
        baseDir = requireNonBlank(baseDir, "baseDir");
        claimedPath = requireNonBlank(claimedPath, "claimedPath");
    }

    private static String requireNonBlank(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value.trim();
    }
}
