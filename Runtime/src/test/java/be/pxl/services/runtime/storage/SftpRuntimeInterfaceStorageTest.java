package be.pxl.services.runtime.storage;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.attribute.FileTime;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;

import org.apache.sshd.sftp.client.SftpClient;
import org.apache.sshd.sftp.common.SftpConstants;
import org.apache.sshd.sftp.common.SftpException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.integration.file.remote.SessionCallback;
import org.springframework.integration.file.remote.session.Session;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;

import be.pxl.services.runtime.domain.ClaimedInterface;
import be.pxl.services.runtime.domain.IncomingInterface;
import be.pxl.services.runtime.exception.RuntimeStorageException;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class SftpRuntimeInterfaceStorageTest {

    private static final Instant FIXED_NOW = Instant.parse("2026-11-27T12:00:00Z");

    private SftpRemoteFileTemplate template;
    private Session<SftpClient.DirEntry> session;
    private SftpRuntimeInterfaceStorage storage;

    @SuppressWarnings("unchecked")
    @BeforeEach
    void setUp() {
        template = mock(SftpRemoteFileTemplate.class);
        session = mock(Session.class);
        when(template.execute(any())).thenAnswer(invocation -> {
            SessionCallback<SftpClient.DirEntry, Object> callback = invocation.getArgument(0);
            return callback.doInSession(session);
        });
        storage = new SftpRuntimeInterfaceStorage(template, "/Clients/", Clock.fixed(FIXED_NOW, ZoneOffset.UTC));
    }

    @Test
    @DisplayName("listReadyIncoming discovers XML files respecting minFileAge, filtering temp files and sorting oldest first")
    void listReadyIncomingFiltersAndSortsFiles() throws Exception {
        when(session.exists("/Clients")).thenReturn(true);
        when(session.list("/Clients")).thenReturn(new SftpClient.DirEntry[] {
                dirEntry("."), dirEntry(".."), dirEntry("../escape"), dirEntry("nouryon")
        });
        when(session.list("/Clients/nouryon")).thenReturn(new SftpClient.DirEntry[] {
                dirEntry("outbound")
        });
        when(session.exists("/Clients/nouryon/outbound/incoming")).thenReturn(true);
        when(session.list("/Clients/nouryon/outbound/incoming")).thenReturn(new SftpClient.DirEntry[] {
                fileEntry("order_new.xml", FIXED_NOW.minusSeconds(1)),      // too young (< 3s)
                fileEntry("order_2.xml", FIXED_NOW.minusSeconds(10)),       // ready (newer)
                fileEntry("order_1.XML", FIXED_NOW.minusSeconds(30)),       // ready (oldest)
                fileEntry("upload.xml.tmp", FIXED_NOW.minusSeconds(60)),    // ignored non-xml
                fileEntry("already.xml.processing", FIXED_NOW.minusSeconds(60)),
                dirEntry("subdir")
        });

        List<IncomingInterface> ready = storage.listReadyIncoming(Duration.ofSeconds(3));

        assertEquals(2, ready.size());
        assertEquals("order_1.XML", ready.get(0).filename());
        assertEquals("nouryon", ready.get(0).customer());
        assertEquals("outbound", ready.get(0).messageType());
        assertEquals("/Clients/nouryon/outbound/incoming/order_1.XML", ready.get(0).remotePath());
        assertEquals("order_2.xml", ready.get(1).filename());
    }

    @Test
    @DisplayName("listReadyIncoming returns empty list when clients root does not exist")
    void listReadyIncomingHandlesMissingRoot() throws Exception {
        when(session.exists("/Clients")).thenReturn(false);

        List<IncomingInterface> ready = storage.listReadyIncoming(Duration.ofSeconds(3));

        assertTrue(ready.isEmpty());
    }

    @Test
    @DisplayName("tryClaim creates processing directory and atomically renames incoming file")
    void tryClaimRenamesFileAtomically() throws Exception {
        IncomingInterface candidate = sampleIncoming();
        when(session.exists("/Clients/nouryon/outbound/processing")).thenReturn(false);

        Optional<ClaimedInterface> claimed = storage.tryClaim(candidate, "runtime-pod-1");

        assertTrue(claimed.isPresent());
        verify(session).mkdir("/Clients/nouryon/outbound/processing");
        ArgumentCaptor<String> targetCaptor = ArgumentCaptor.forClass(String.class);
        verify(session).rename(eq(candidate.remotePath()), targetCaptor.capture());
        String claimedPath = targetCaptor.getValue();
        assertTrue(claimedPath.startsWith("/Clients/nouryon/outbound/processing/order_1.xml.runtime-pod-1."));
        assertTrue(claimedPath.endsWith(".processing"));
        assertEquals(claimedPath, claimed.get().claimedPath());
    }

    @Test
    @DisplayName("tryClaim returns empty Optional when another pod already claimed the file (NO_SUCH_FILE)")
    void tryClaimReturnsEmptyWhenAlreadyClaimed() throws Exception {
        IncomingInterface candidate = sampleIncoming();
        when(session.exists("/Clients/nouryon/outbound/processing")).thenReturn(true);
        doThrow(new SftpException(SftpConstants.SSH_FX_NO_SUCH_FILE, "No such file"))
                .when(session).rename(eq(candidate.remotePath()), anyString());

        Optional<ClaimedInterface> claimed = storage.tryClaim(candidate, "runtime-pod-2");

        assertTrue(claimed.isEmpty());
    }

    @Test
    @DisplayName("tryClaim throws RuntimeStorageException on non-race SFTP errors")
    void tryClaimThrowsOnStorageFailure() throws Exception {
        IncomingInterface candidate = sampleIncoming();
        when(session.exists("/Clients/nouryon/outbound/processing")).thenReturn(true);
        doThrow(new SftpException(SftpConstants.SSH_FX_PERMISSION_DENIED, "Permission denied"))
                .when(session).rename(eq(candidate.remotePath()), anyString());

        assertThrows(RuntimeStorageException.class, () -> storage.tryClaim(candidate, "runtime-pod-1"));
    }

    @Test
    @DisplayName("readBytes reads claimed XML payload completely in memory")
    void readBytesStreamsXmlInMemory() throws Exception {
        ClaimedInterface claimed = sampleClaimed();
        byte[] expected = "<DELVRY03><IDOC/></DELVRY03>".getBytes(StandardCharsets.UTF_8);
        doAnswer(invocation -> {
            OutputStream out = invocation.getArgument(1);
            out.write(expected);
            return null;
        }).when(session).read(eq(claimed.claimedPath()), any(OutputStream.class));

        byte[] actual = storage.readBytes(claimed);

        assertArrayEquals(expected, actual);
    }

    @Test
    @DisplayName("moveToProcessed renames claimed file into processed/ and avoids filename collisions")
    void moveToProcessedHandlesCollisions() throws Exception {
        ClaimedInterface claimed = sampleClaimed();
        when(session.exists("/Clients/nouryon/outbound/processed")).thenReturn(true);
        when(session.exists("/Clients/nouryon/outbound/processed/order_1.xml")).thenReturn(true);

        storage.moveToProcessed(claimed);

        String expectedDest = "/Clients/nouryon/outbound/processed/order_1_" + FIXED_NOW.toEpochMilli() + ".xml";
        verify(session).rename(claimed.claimedPath(), expectedDest);
    }

    @Test
    @DisplayName("moveToError moves claimed file to error/ and writes companion .error.txt note")
    void moveToErrorMovesFileAndWritesReason() throws Exception {
        ClaimedInterface claimed = sampleClaimed();
        when(session.exists("/Clients/nouryon/outbound/error")).thenReturn(false);
        when(session.exists("/Clients/nouryon/outbound/error/order_1.xml")).thenReturn(false);

        ByteArrayOutputStream capturedNote = new ByteArrayOutputStream();
        doAnswer(invocation -> {
            InputStream in = invocation.getArgument(0);
            in.transferTo(capturedNote);
            return null;
        }).when(session).write(any(InputStream.class), eq("/Clients/nouryon/outbound/error/order_1.xml.error.txt"));

        storage.moveToError(claimed, "Interface is geen geldig XML");

        verify(session).mkdir("/Clients/nouryon/outbound/error");
        verify(session).rename(claimed.claimedPath(), "/Clients/nouryon/outbound/error/order_1.xml");
        String note = capturedNote.toString(StandardCharsets.UTF_8);
        assertTrue(note.contains("customer=nouryon"));
        assertTrue(note.contains("reason=Interface is geen geldig XML"));
    }

    @Test
    @DisplayName("recoverStaleClaims returns expired .processing files back to incoming/")
    void recoverStaleClaimsRestoresExpiredFiles() throws Exception {
        when(session.exists("/Clients")).thenReturn(true);
        when(session.list("/Clients")).thenReturn(new SftpClient.DirEntry[] { dirEntry("nouryon") });
        when(session.list("/Clients/nouryon")).thenReturn(new SftpClient.DirEntry[] { dirEntry("outbound") });
        when(session.exists("/Clients/nouryon/outbound/processing")).thenReturn(true);
        when(session.list("/Clients/nouryon/outbound/processing")).thenReturn(new SftpClient.DirEntry[] {
                fileEntry("order_1.xml.pod-dead.a1b2c3d4.processing", FIXED_NOW.minus(Duration.ofMinutes(10))),
                fileEntry("order_2.xml.pod-live.e5f6g7h8.processing", FIXED_NOW.minus(Duration.ofMinutes(1)))
        });
        when(session.exists("/Clients/nouryon/outbound/incoming")).thenReturn(true);
        when(session.exists("/Clients/nouryon/outbound/incoming/order_1.xml")).thenReturn(false);

        int recovered = storage.recoverStaleClaims(Duration.ofMinutes(5));

        assertEquals(1, recovered);
        verify(session).rename(
                "/Clients/nouryon/outbound/processing/order_1.xml.pod-dead.a1b2c3d4.processing",
                "/Clients/nouryon/outbound/incoming/order_1.xml"
        );
    }

    @Test
    @DisplayName("extractOriginalFilename strips instanceId, claim token and .processing suffix")
    void extractOriginalFilenameStripsSuffixes() {
        assertEquals(
                "order_1.xml",
                SftpInterfacePathSupport.extractOriginalFilename("order_1.xml.pod-a.12ab34cd.processing")
        );
        assertEquals(
                "ORDER.XML",
                SftpInterfacePathSupport.extractOriginalFilename("ORDER.XML.pod-b.99ff00aa.processing")
        );
    }

    private IncomingInterface sampleIncoming() {
        return new IncomingInterface(
                "nouryon",
                "outbound",
                "order_1.xml",
                "/Clients/nouryon/outbound",
                "/Clients/nouryon/outbound/incoming/order_1.xml",
                FIXED_NOW.minusSeconds(30)
        );
    }

    private ClaimedInterface sampleClaimed() {
        return new ClaimedInterface(
                "nouryon",
                "outbound",
                "order_1.xml",
                "/Clients/nouryon/outbound",
                "/Clients/nouryon/outbound/processing/order_1.xml.pod-a.12345678.processing"
        );
    }

    private SftpClient.DirEntry dirEntry(String name) {
        SftpClient.Attributes attrs = new SftpClient.Attributes();
        attrs.setType(SftpConstants.SSH_FILEXFER_TYPE_DIRECTORY);
        attrs.setModifyTime(FileTime.from(FIXED_NOW));
        return new SftpClient.DirEntry(name, name, attrs);
    }

    private SftpClient.DirEntry fileEntry(String name, Instant modifiedAt) {
        SftpClient.Attributes attrs = new SftpClient.Attributes();
        attrs.setType(SftpConstants.SSH_FILEXFER_TYPE_REGULAR);
        attrs.setModifyTime(FileTime.from(modifiedAt));
        return new SftpClient.DirEntry(name, name, attrs);
    }
}
