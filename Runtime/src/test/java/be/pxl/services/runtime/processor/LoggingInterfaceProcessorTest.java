package be.pxl.services.runtime.processor;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import be.pxl.services.runtime.domain.ClaimedInterface;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

class LoggingInterfaceProcessorTest {

    private final LoggingInterfaceProcessor processor = new LoggingInterfaceProcessor();

    @Test
    @DisplayName("LoggingInterfaceProcessor accepts non-empty XML payloads")
    void processesValidPayload() {
        ClaimedInterface claimed = new ClaimedInterface(
                "nouryon", "outbound", "order1.xml", "/Clients/nouryon/outbound",
                "/Clients/nouryon/outbound/processing/order1.xml.pod1.processing"
        );

        assertDoesNotThrow(() -> processor.process(claimed, "<order/>".getBytes(StandardCharsets.UTF_8)));
    }

    @Test
    @DisplayName("LoggingInterfaceProcessor rejects null metadata or empty payloads")
    void rejectsInvalidInputs() {
        ClaimedInterface claimed = new ClaimedInterface(
                "nouryon", "outbound", "order1.xml", "/Clients/nouryon/outbound",
                "/Clients/nouryon/outbound/processing/order1.xml.pod1.processing"
        );

        assertThrows(IllegalArgumentException.class, () -> processor.process(null, "<x/>".getBytes(StandardCharsets.UTF_8)));
        assertThrows(IllegalArgumentException.class, () -> processor.process(claimed, null));
        assertThrows(IllegalArgumentException.class, () -> processor.process(claimed, new byte[0]));
    }
}
