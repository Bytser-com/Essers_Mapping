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
import be.pxl.services.runtime.exception.InterfacePayloadTooLargeException;
import be.pxl.services.runtime.exception.RuntimeStorageException;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
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
    private static final long MAX_FILE_BYTES = 1_024L;

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
        storage = new SftpRuntimeInterfaceStorage(
                template, "/Clients/", MAX_FILE_BYTES, Clock.fixed(FIXED_NOW, ZoneOffset.UTC));
    }

    @Test
    @DisplayName("listReadyIncoming filters hidden files, symlinks, control chars, young files and sorts oldest first")
    void listReadyIncomingFiltersAndSortsFiles() throws Exception {
        when(session.list("/Clients")).thenReturn(new SftpClient.DirEntry[] {
                dirEntry("."), dirEntry(".."), dirEntry("../escape"), dirEntry(".hidden"), dirEntry("nouryon")
        });
        when(session.list("/Clients/nouryon")).thenReturn(new SftpClient.DirEntry[] {
                dirEntry("outbound")
        });
        when(session.list("/Clients/nouryon/outbound/incoming")).thenReturn(new SftpClient.DirEntry[] {
                fileEntry("order_new.xml", FIXED_NOW.minusSeconds(1)),
                fileEntry("order_2.xml", FIXED_NOW.minusSeconds(10)),
                fileEntry("order..1.XML", FIXED_NOW.minusSeconds(30)),
                fileEntry(".temp_upload.xml", FIXED_NOW.minusSeconds(60)),
                fileEntry("bad\nname.xml", FIXED_NOW.minusSeconds(60)),
                symlinkEntry("link.xml", FIXED_NOW.minusSeconds(60)),
                fileEntryWithoutMtime("nomtime.xml"),
                fileEntry("upload.xml.tmp", FIXED_NOW.minusSeconds(60)),
                fileEntry("already.xml.processing", FIXED_NOW.minusSeconds(60)),
                dirEntry("subdir")
        });

        List<IncomingInterface> ready = storage.listReadyIncoming(Duration.ofSeconds(3));

        assertEquals(2, ready.size());
        assertEquals("order..1.XML", ready.get(0).filename());
        assertEquals("nouryon", ready.get(0).customer());
        assertEquals("outbound", ready.get(0).messageType());
        assertEquals("/Clients/nouryon/outbound/incoming/order..1.XML", ready.get(0).remotePath());
        assertEquals("order_2.xml", ready.get(1).filename());
    }

    @Test
    @DisplayName("listReadyIncoming returns empty list when clients root does not exist")
    void listReadyIncomingHandlesMissingRoot() throws Exception {
        when(session.list("/Clients")).thenThrow(new SftpException(SftpConstants.SSH_FX_NO_SUCH_FILE, "No such file"));

        List<IncomingInterface> ready = storage.listReadyIncoming(Duration.ofSeconds(3));

        assertTrue(ready.isEmpty());
    }

    @Test
    @DisplayName("listReadyIncoming isolates one broken customer folder so other customers are still scanned")
    void listReadyIncomingIsolatesCustomerErrors() throws Exception {
        when(session.list("/Clients")).thenReturn(new SftpClient.DirEntry[] {
                dirEntry("broken-client"), dirEntry("nouryon")
        });
        when(session.list("/Clients/broken-client"))
                .thenThrow(new SftpException(SftpConstants.SSH_FX_PERMISSION_DENIED, "Permission denied"));
        when(session.list("/Clients/nouryon")).thenReturn(new SftpClient.DirEntry[] { dirEntry("outbound") });
        when(session.list("/Clients/nouryon/outbound/incoming")).thenReturn(new SftpClient.DirEntry[] {
                fileEntry("order_1.xml", FIXED_NOW.minusSeconds(30))
        });

        List<IncomingInterface> ready = storage.listReadyIncoming(Duration.ofSeconds(3));

        assertEquals(1, ready.size());
        assertEquals("nouryon", ready.get(0).customer());
    }

    @Test
    @DisplayName("tryClaim embeds claim epochMillis in processing filename and tolerates mkdir race")
    void tryClaimRenamesFileWithClaimTimestampAndToleratesMkdirRace() throws Exception {
        IncomingInterface candidate = sampleIncoming();
        when(session.exists("/Clients/nouryon/outbound/processing")).thenReturn(false, true);
        doThrow(new IOException("Directory already exists"))
                .when(session).mkdir("/Clients/nouryon/outbound/processing");

        Optional<ClaimedInterface> claimed = storage.tryClaim(candidate, "runtime-pod.1");

        assertTrue(claimed.isPresent());
        verify(session).mkdir("/Clients/nouryon/outbound/processing");
        ArgumentCaptor<String> targetCaptor = ArgumentCaptor.forClass(String.class);
        verify(session).rename(eq(candidate.remotePath()), targetCaptor.capture());
        String claimedPath = targetCaptor.getValue();
        String expectedPrefix = "/Clients/nouryon/outbound/processing/order_1.xml."
                + FIXED_NOW.toEpochMilli() + ".runtime-pod-1.";
        assertTrue(claimedPath.startsWith(expectedPrefix), "Unexpected claimedPath: " + claimedPath);
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
    @DisplayName("readBytes reads claimed XML payload completely in memory within size limit")
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
    @DisplayName("readBytes throws InterfacePayloadTooLargeException when file exceeds maxFileSizeBytes")
    void readBytesRejectsOversizedPayload() throws Exception {
        ClaimedInterface claimed = sampleClaimed();
        byte[] oversized = new byte[(int) MAX_FILE_BYTES + 1];
        doAnswer(invocation -> {
            OutputStream out = invocation.getArgument(1);
            out.write(oversized);
            return null;
        }).when(session).read(eq(claimed.claimedPath()), any(OutputStream.class));

        assertThrows(InterfacePayloadTooLargeException.class, () -> storage.readBytes(claimed));
    }

    @Test
    @DisplayName("moveToProcessed avoids same-millisecond filename collisions with timestamp and token")
    void moveToProcessedHandlesCollisions() throws Exception {
        ClaimedInterface claimed = sampleClaimed();
        when(session.exists("/Clients/nouryon/outbound/processed")).thenReturn(true);
        when(session.exists("/Clients/nouryon/outbound/processed/order_1.xml")).thenReturn(true);

        storage.moveToProcessed(claimed);

        ArgumentCaptor<String> destCaptor = ArgumentCaptor.forClass(String.class);
        verify(session).rename(eq(claimed.claimedPath()), destCaptor.capture());
        String dest = destCaptor.getValue();
        assertTrue(dest.startsWith("/Clients/nouryon/outbound/processed/order_1_" + FIXED_NOW.toEpochMilli() + "_"));
        assertTrue(dest.endsWith(".xml"));
    }

    @Test
    @DisplayName("moveToError moves claimed file to error/ and sanitizes multiline reason in .error.txt")
    void moveToErrorMovesFileAndWritesSanitizedReason() throws Exception {
        ClaimedInterface claimed = sampleClaimed();
        when(session.exists("/Clients/nouryon/outbound/error")).thenReturn(false);
        when(session.exists("/Clients/nouryon/outbound/error/order_1.xml")).thenReturn(false);

        ByteArrayOutputStream capturedNote = new ByteArrayOutputStream();
        doAnswer(invocation -> {
            InputStream in = invocation.getArgument(0);
            in.transferTo(capturedNote);
            return null;
        }).when(session).write(any(InputStream.class), eq("/Clients/nouryon/outbound/error/order_1.xml.error.txt"));

        storage.moveToError(claimed, "Invalid XML payload\nline2\r\nline3");

        verify(session).mkdir("/Clients/nouryon/outbound/error");
        verify(session).rename(claimed.claimedPath(), "/Clients/nouryon/outbound/error/order_1.xml");
        String note = capturedNote.toString(StandardCharsets.UTF_8);
        assertTrue(note.contains("customer=nouryon"));
        assertTrue(note.contains("reason=Invalid XML payload line2  line3"));
    }

    @Test
    @DisplayName("recoverStaleClaims uses embedded claim timestamp instead of POSIX file mtime")
    void recoverStaleClaimsUsesClaimTimestampNotMtime() throws Exception {
        long staleClaimMs = FIXED_NOW.minus(Duration.ofMinutes(10)).toEpochMilli();
        long freshClaimMs = FIXED_NOW.minus(Duration.ofMinutes(1)).toEpochMilli();

        when(session.list("/Clients")).thenReturn(new SftpClient.DirEntry[] { dirEntry("nouryon") });
        when(session.list("/Clients/nouryon")).thenReturn(new SftpClient.DirEntry[] { dirEntry("outbound") });
        when(session.list("/Clients/nouryon/outbound/processing")).thenReturn(new SftpClient.DirEntry[] {
                // Stale claim timestamp (10m ago), even with fresh mtime -> MUST recover
                fileEntry("order_1.xml." + staleClaimMs + ".pod-dead.a1b2c3d4.processing", FIXED_NOW),
                // Fresh claim timestamp (1m ago), even with OLD upload mtime (30m ago) -> MUST NOT recover!
                fileEntry("order_2.xml." + freshClaimMs + ".pod-live.e5f6g7h8.processing",
                        FIXED_NOW.minus(Duration.ofMinutes(30)))
        });
        when(session.exists("/Clients/nouryon/outbound/incoming")).thenReturn(true);
        when(session.exists("/Clients/nouryon/outbound/incoming/order_1.xml")).thenReturn(false);

        int recovered = storage.recoverStaleClaims(Duration.ofMinutes(5));

        assertEquals(1, recovered);
        verify(session).rename(
                "/Clients/nouryon/outbound/processing/order_1.xml." + staleClaimMs + ".pod-dead.a1b2c3d4.processing",
                "/Clients/nouryon/outbound/incoming/order_1.xml"
        );
    }

    @Test
    @DisplayName("extractOriginalFilename parses both claim-timestamp and legacy formats cleanly")
    void extractOriginalFilenameParsesFormats() {
        assertEquals(
                "order_1.xml",
                SftpInterfacePathSupport.extractOriginalFilename(
                        "order_1.xml.1764244800000.pod-xml-1.12ab34cd.processing")
        );
        assertEquals(
                "ORDER.XML",
                SftpInterfacePathSupport.extractOriginalFilename("ORDER.XML.pod-b.99ff00aa.processing")
        );
        assertFalse(SftpInterfacePathSupport.isSafeSegment(".hidden.xml"));
        assertTrue(SftpInterfacePathSupport.isSafeSegment("order..1.xml"));
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
                "/Clients/nouryon/outbound/processing/order_1.xml."
                        + FIXED_NOW.toEpochMilli() + ".pod-a.12345678.processing"
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

    private SftpClient.DirEntry fileEntryWithoutMtime(String name) {
        SftpClient.Attributes attrs = new SftpClient.Attributes();
        attrs.setType(SftpConstants.SSH_FILEXFER_TYPE_REGULAR);
        return new SftpClient.DirEntry(name, name, attrs);
    }

    private SftpClient.DirEntry symlinkEntry(String name, Instant modifiedAt) {
        SftpClient.Attributes attrs = new SftpClient.Attributes();
        attrs.setType(SftpConstants.SSH_FILEXFER_TYPE_SYMLINK);
        attrs.setPermissions(SftpConstants.S_IFLNK | 0777);
        attrs.setModifyTime(FileTime.from(modifiedAt));
        return new SftpClient.DirEntry(name, name, attrs);
    }
}
