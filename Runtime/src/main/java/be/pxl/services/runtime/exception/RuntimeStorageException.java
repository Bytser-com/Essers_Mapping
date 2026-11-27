package be.pxl.services.runtime.exception;

/**
 * Thrown when communication with the Runtime SFTP storage fails.
 */
public class RuntimeStorageException extends RuntimeException {

    public RuntimeStorageException(String message) {
        super(message);
    }

    public RuntimeStorageException(String message, Throwable cause) {
        super(message, cause);
    }
}
