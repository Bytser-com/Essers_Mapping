package be.pxl.services.runtime.exception;

/**
 * Thrown when communication with the shared SFTP storage (mapping packages) fails.
 */
public class SharedStorageException extends RuntimeException {

    public SharedStorageException(String message) {
        super(message);
    }

    public SharedStorageException(String message, Throwable cause) {
        super(message, cause);
    }
}
