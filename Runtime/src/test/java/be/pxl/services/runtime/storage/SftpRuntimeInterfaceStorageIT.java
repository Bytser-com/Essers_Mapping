package be.pxl.services.runtime.storage;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import org.apache.sshd.common.file.virtualfs.VirtualFileSystemFactory;
import org.apache.sshd.server.SshServer;
import org.apache.sshd.server.keyprovider.SimpleGeneratorHostKeyProvider;
import org.apache.sshd.sftp.client.SftpClient;
import org.apache.sshd.sftp.server.SftpSubsystemFactory;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.integration.file.remote.session.CachingSessionFactory;
import org.springframework.integration.sftp.session.DefaultSftpSessionFactory;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;

import be.pxl.services.runtime.domain.ClaimedInterface;
import be.pxl.services.runtime.domain.IncomingInterface;
import be.pxl.services.runtime.exception.InterfacePayloadTooLargeException;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Real end-to-end SFTP integration test against an embedded Apache MINA SSHD server.
 * Proves real POSIX SFTP rename atomicity, no-overwrite safety on collisions, claim-timestamp
 * stale recovery (immune to POSIX mtime preservation), upfront stat() size limits, and clean teardown.
 */
class SftpRuntimeInterfaceStorageIT {

    private static final String SFTP_USER = "runtime-it-user";
    private static final long MAX_FILE_BYTES = 512L;

    @TempDir
    Path tempDir;

    private Path sftpHome;
    private SshServer sshServer;
    private DefaultSftpSessionFactory delegateFactory;
    private CachingSessionFactory<SftpClient.DirEntry> cachingFactory;
    private MutableClock testClock;
    private SftpRuntimeInterfaceStorage storage;

    @BeforeEach
    void setUp() throws Exception {
        sftpHome = Files.createDirectories(tempDir.resolve("sftp-home"));
        Path hostKeyPath = tempDir.resolve("hostkey.ser");
        String ephemeralPass = UUID.randomUUID().toString();

        sshServer = SshServer.setUpDefaultServer();
        sshServer.setPort(0);
        sshServer.setKeyPairProvider(new SimpleGeneratorHostKeyProvider(hostKeyPath));
        sshServer.setPasswordAuthenticator((username, password, session) ->
                SFTP_USER.equals(username) && ephemeralPass.equals(password));
        sshServer.setSubsystemFactories(List.of(new SftpSubsystemFactory()));
        sshServer.setFileSystemFactory(new VirtualFileSystemFactory(sftpHome));
        sshServer.start();

        delegateFactory = new DefaultSftpSessionFactory(false);
        delegateFactory.setHost("127.0.0.1");
        delegateFactory.setPort(sshServer.getPort());
        delegateFactory.setUser(SFTP_USER);
        delegateFactory.setPassword(ephemeralPass);
        delegateFactory.setTimeout(5_000);
        delegateFactory.setAllowUnknownKeys(true);

        cachingFactory = new CachingSessionFactory<>(delegateFactory, 4);
        cachingFactory.setTestSession(true);

        testClock = new MutableClock(Instant.now());
        storage = new SftpRuntimeInterfaceStorage(
                new SftpRemoteFileTemplate(cachingFactory), "/Clients", MAX_FILE_BYTES, testClock);
    }

    @AfterEach
    void tearDown() throws Exception {
        if (cachingFactory != null) {
            cachingFactory.destroy();
        }
        if (delegateFactory != null) {
            delegateFactory.destroy();
        }
        if (sshServer != null) {
            sshServer.stop(true);
        }
    }

    @Test
    @DisplayName("Real POSIX SFTP rename keeps old upload mtime, yet claim-timestamp prevents premature stale recovery")
    void realPosixRenameDoesNotCausePrematureStaleRecovery() throws Exception {
        Path incomingDir = Files.createDirectories(sftpHome.resolve("Clients/nouryon/outbound/incoming"));
        Path backlogFile = incomingDir.resolve("backlog_order.xml");
        byte[] payload = "<DELVRY03><IDOC>backlog</IDOC></DELVRY03>".getBytes(StandardCharsets.UTF_8);
        Files.write(backlogFile, payload);
        Files.setLastModifiedTime(backlogFile, FileTime.from(testClock.instant().minus(Duration.ofMinutes(10))));

        Path hiddenFile = incomingDir.resolve(".uploading.xml");
        Files.writeString(hiddenFile, "<tmp/>");
        Files.setLastModifiedTime(hiddenFile, FileTime.from(testClock.instant().minus(Duration.ofMinutes(10))));

        List<IncomingInterface> ready = storage.listReadyIncoming(Duration.ofSeconds(3));
        assertEquals(1, ready.size());
        assertEquals("backlog_order.xml", ready.get(0).filename());

        Optional<ClaimedInterface> podAClaim = storage.tryClaim(ready.get(0), "pod-a");
        assertTrue(podAClaim.isPresent());
        assertTrue(storage.tryClaim(ready.get(0), "pod-b").isEmpty());
        assertArrayEquals(payload, storage.readBytes(podAClaim.get()));

        // 1s later: old upload mtime must NOT cause stale recovery
        testClock.advance(Duration.ofSeconds(1));
        assertEquals(0, storage.recoverStaleClaims(Duration.ofMinutes(5)));
        assertFalse(Files.exists(backlogFile));

        // Simulate customer uploading a brand-new order with the SAME filename while Pod A is stale!
        String newCustomerOrder = "<DELVRY03><IDOC>brand-new-order</IDOC></DELVRY03>";
        Files.writeString(backlogFile, newCustomerOrder);

        // 6m later: stale recovery must NOT overwrite the new customer upload; it must use a collision-free name!
        testClock.advance(Duration.ofMinutes(6));
        assertEquals(1, storage.recoverStaleClaims(Duration.ofMinutes(5)));
        assertEquals(newCustomerOrder, Files.readString(backlogFile),
                "New customer upload in incoming/ must never be overwritten by stale recovery");
        try (var files = Files.list(incomingDir)) {
            long xmlCount = files.filter(p -> p.getFileName().toString().startsWith("backlog_order")).count();
            assertEquals(2L, xmlCount, "Both new upload and recovered stale claim must exist in incoming/");
        }
    }

    @Test
    @DisplayName("Real SFTP storage enforces maxFileSizeBytes, moves processed without overwrite, and writes error notes")
    void realSftpTransitionsAndSizeLimitWorkEndToEnd() throws Exception {
        Path incomingDir = Files.createDirectories(sftpHome.resolve("Clients/nouryon/outbound/incoming"));
        Path okFile = incomingDir.resolve("order_ok.xml");
        Path bigFile = incomingDir.resolve("order_big.xml");
        Files.writeString(okFile, "<order id=\"1\"/>");
        Files.write(bigFile, new byte[(int) MAX_FILE_BYTES + 16]);
        Instant oldTime = testClock.instant().minus(Duration.ofSeconds(30));
        Files.setLastModifiedTime(okFile, FileTime.from(oldTime));
        Files.setLastModifiedTime(bigFile, FileTime.from(oldTime));

        // Pre-populate processed/order_ok.xml to prove no-overwrite collision handling on real SFTP
        Path processedDir = Files.createDirectories(sftpHome.resolve("Clients/nouryon/outbound/processed"));
        Path existingProcessed = processedDir.resolve("order_ok.xml");
        Files.writeString(existingProcessed, "<previous/>");

        List<IncomingInterface> ready = storage.listReadyIncoming(Duration.ofSeconds(3));
        assertEquals(2, ready.size());

        IncomingInterface okCandidate = ready.stream()
                .filter(f -> f.filename().equals("order_ok.xml")).findFirst().orElseThrow();
        IncomingInterface bigCandidate = ready.stream()
                .filter(f -> f.filename().equals("order_big.xml")).findFirst().orElseThrow();

        ClaimedInterface okClaim = storage.tryClaim(okCandidate, "pod-1").orElseThrow();
        storage.moveToProcessed(okClaim);
        assertEquals("<previous/>", Files.readString(existingProcessed),
                "Previously processed file must never be overwritten");
        try (var processedFiles = Files.list(processedDir)) {
            assertEquals(2L, processedFiles.count(), "Both original and collision-safe file must exist");
        }

        ClaimedInterface bigClaim = storage.tryClaim(bigCandidate, "pod-1").orElseThrow();
        InterfacePayloadTooLargeException sizeEx =
                assertThrows(InterfacePayloadTooLargeException.class, () -> storage.readBytes(bigClaim));
        storage.moveToError(bigClaim, sizeEx.getClass().getSimpleName() + ": " + sizeEx.getMessage());

        Path errorDir = sftpHome.resolve("Clients/nouryon/outbound/error");
        assertTrue(Files.exists(errorDir.resolve("order_big.xml")));
        Path errorNote = errorDir.resolve("order_big.xml.error.txt");
        assertTrue(Files.exists(errorNote));
        String noteContent = Files.readString(errorNote, StandardCharsets.UTF_8);
        assertTrue(noteContent.contains("InterfacePayloadTooLargeException"));
    }

    private static final class MutableClock extends Clock {

        private Instant current;

        MutableClock(Instant initial) {
            this.current = initial;
        }

        void advance(Duration delta) {
            this.current = this.current.plus(delta);
        }

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return this;
        }

        @Override
        public Instant instant() {
            return current;
        }
    }
}
