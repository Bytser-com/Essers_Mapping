package be.pxl.services.runtime.exception;

import java.net.URI;
import java.time.Instant;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * Turns exceptions into a JSON error response, in the same format as Version_Control.
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

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

    // The SFTP storage cannot be reached or read: the problem is not in the request
    @ExceptionHandler(SharedStorageException.class)
    public ProblemDetail handleSharedStorage(SharedStorageException ex) {
        return problem(HttpStatus.BAD_GATEWAY, "SFTP Storage Error", ex.getMessage());
    }

    private ProblemDetail problem(HttpStatus status, String title, String detail) {
        ProblemDetail problemDetail = ProblemDetail.forStatusAndDetail(status, detail);
        problemDetail.setTitle(title);
        problemDetail.setType(URI.create("about:blank"));
        problemDetail.setProperty("timestamp", Instant.now());
        return problemDetail;
    }
}
