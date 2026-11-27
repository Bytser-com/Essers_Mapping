package be.pxl.services.runtime.domain;

import java.time.Instant;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import be.pxl.services.runtime.exception.RuntimeStorageException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

class InterfaceDomainTest {

    @Test
    @DisplayName("IncomingInterface preserves exact values and rejects blank, padded or null fields")
    void incomingInterfaceValidatesFields() {
        Instant now = Instant.now();
        IncomingInterface item = new IncomingInterface(
                "nouryon", "outbound", "order1.xml", "/Clients/nouryon/outbound",
                "/Clients/nouryon/outbound/incoming/order1.xml", now
        );

        assertEquals("nouryon", item.customer());
        assertEquals("outbound", item.messageType());
        assertEquals("order1.xml", item.filename());
        assertEquals(now, item.lastModified());

        assertThrows(IllegalArgumentException.class, () -> new IncomingInterface(
                " ", "outbound", "order1.xml", "/Clients/nouryon/outbound",
                "/Clients/nouryon/outbound/incoming/order1.xml", now
        ));
        assertThrows(IllegalArgumentException.class, () -> new IncomingInterface(
                "nouryon", "outbound ", "order1.xml", "/Clients/nouryon/outbound",
                "/Clients/nouryon/outbound/incoming/order1.xml", now
        ));
        assertThrows(NullPointerException.class, () -> new IncomingInterface(
                "nouryon", "outbound", "order1.xml", "/Clients/nouryon/outbound",
                "/Clients/nouryon/outbound/incoming/order1.xml", null
        ));
    }

    @Test
    @DisplayName("ClaimedInterface preserves exact values and rejects blank or whitespace-padded fields")
    void claimedInterfaceValidatesFields() {
        ClaimedInterface claimed = new ClaimedInterface(
                "nouryon", "inbound", "order1.xml", "/Clients/nouryon/inbound",
                "/Clients/nouryon/inbound/processing/order1.xml.pod1.processing"
        );

        assertEquals("nouryon", claimed.customer());
        assertEquals("inbound", claimed.messageType());
        assertEquals("order1.xml", claimed.filename());

        assertThrows(IllegalArgumentException.class, () -> new ClaimedInterface(
                "nouryon", "inbound", "", "/Clients/nouryon/inbound",
                "/Clients/nouryon/inbound/processing/order1.xml.pod1.processing"
        ));
        assertThrows(IllegalArgumentException.class, () -> new ClaimedInterface(
                " nouryon", "inbound", "order1.xml", "/Clients/nouryon/inbound",
                "/Clients/nouryon/inbound/processing/order1.xml.pod1.processing"
        ));
    }

    @Test
    @DisplayName("RuntimeStorageException preserves message and cause")
    void storageExceptionPreservesContext() {
        IllegalStateException cause = new IllegalStateException("SFTP closed");
        RuntimeStorageException withCause = new RuntimeStorageException("Read failed", cause);
        RuntimeStorageException messageOnly = new RuntimeStorageException("Not found");

        assertEquals("Read failed", withCause.getMessage());
        assertSame(cause, withCause.getCause());
        assertEquals("Not found", messageOnly.getMessage());
    }
}
