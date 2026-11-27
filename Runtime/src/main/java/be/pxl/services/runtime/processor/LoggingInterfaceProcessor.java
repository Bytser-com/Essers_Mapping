package be.pxl.services.runtime.processor;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Fallback;
import org.springframework.stereotype.Component;

import be.pxl.services.runtime.domain.ClaimedInterface;

/**
 * Default fallback processor for US IT2627T06-56 that rejects empty payloads
 * and logs each fetched interface until downstream XML parsing and conversion
 * (US 52/152/55) are wired into {@link InterfaceProcessor}.
 */
@Component
@Fallback
public class LoggingInterfaceProcessor implements InterfaceProcessor {

    private static final Logger LOGGER = LoggerFactory.getLogger(LoggingInterfaceProcessor.class);

    @Override
    public void process(ClaimedInterface claimedInterface, byte[] xmlContent) {
        if (claimedInterface == null) {
            throw new IllegalArgumentException("claimedInterface must not be null");
        }
        if (xmlContent == null || xmlContent.length == 0) {
            throw new IllegalArgumentException(
                    "Interface payload is empty for file: " + claimedInterface.filename());
        }
        LOGGER.info("Fetched customer interface customer={} type={} file={} sizeBytes={}",
                claimedInterface.customer(),
                claimedInterface.messageType(),
                claimedInterface.filename(),
                xmlContent.length);
    }
}
