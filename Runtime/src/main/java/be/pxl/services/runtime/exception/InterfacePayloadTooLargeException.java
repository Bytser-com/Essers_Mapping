package be.pxl.services.runtime.exception;

/**
 * Thrown when a claimed customer interface exceeds the configured maximum in-memory size limit.
 * Intentionally distinct from {@link RuntimeStorageException} so the poller quarantines oversized
 * files into {@code error/} rather than retrying them as transient SFTP failures.
 */
public class InterfacePayloadTooLargeException extends RuntimeException {

    public InterfacePayloadTooLargeException(String message) {
        super(message);
    }
}
