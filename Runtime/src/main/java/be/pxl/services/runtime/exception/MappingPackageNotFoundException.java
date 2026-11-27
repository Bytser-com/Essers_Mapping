package be.pxl.services.runtime.exception;

/**
 * Thrown when a customer has no mapping package for the requested package type.
 */
public class MappingPackageNotFoundException extends RuntimeException {

    public MappingPackageNotFoundException(String message) {
        super(message);
    }
}
