package be.pxl.services.runtime.exception;

import java.net.URI;
import java.time.Instant;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.ErrorResponse;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * Turns exceptions into a JSON error response, in the same format as Version_Control.
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger LOGGER = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(MappingPackageNotFoundException.class)
    public ProblemDetail handleMappingPackageNotFound(MappingPackageNotFoundException ex) {
        return problem(HttpStatus.NOT_FOUND, "Mapping Package Not Found", ex.getMessage());
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ProblemDetail handleIllegalArgument(IllegalArgumentException ex) {
        return problem(HttpStatus.BAD_REQUEST, "Invalid Request Parameter", ex.getMessage());
    }

    @ExceptionHandler(MissingServletRequestParameterException.class)
    public ProblemDetail handleMissingParameter(MissingServletRequestParameterException ex) {
        return problem(HttpStatus.BAD_REQUEST, "Missing Required Parameter", ex.getMessage());
    }

    // The SFTP storage cannot be reached or read. The details (with SFTP paths) only go to the log.
    @ExceptionHandler(SharedStorageException.class)
    public ProblemDetail handleSharedStorage(SharedStorageException ex) {
        LOGGER.error("Mapping package storage error", ex);
        return problem(HttpStatus.BAD_GATEWAY, "SFTP Storage Error", "The mapping package storage could not be read.");
    }

    @ExceptionHandler(Exception.class)
    public ProblemDetail handleUnexpected(Exception ex) {
        // Spring's own errors (unknown URL, wrong method, ...) keep their status, e.g. 404 or 405
        if (ex instanceof ErrorResponse errorResponse) {
            return errorResponse.getBody();
        }
        LOGGER.error("Unexpected error", ex);
        return problem(HttpStatus.INTERNAL_SERVER_ERROR, "Internal Server Error", "An unexpected error occurred");
    }

    private ProblemDetail problem(HttpStatus status, String title, String detail) {
        ProblemDetail problemDetail = ProblemDetail.forStatusAndDetail(status, detail);
        problemDetail.setTitle(title);
        problemDetail.setType(URI.create("about:blank"));
        problemDetail.setProperty("timestamp", Instant.now());
        return problemDetail;
    }
}
