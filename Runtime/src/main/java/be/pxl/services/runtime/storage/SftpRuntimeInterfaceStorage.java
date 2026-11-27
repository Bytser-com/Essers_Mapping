package be.pxl.services.runtime.storage;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

import org.apache.sshd.sftp.client.SftpClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.file.remote.session.Session;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;
import org.springframework.stereotype.Service;

import be.pxl.services.runtime.config.RuntimeSftpConfig;
import be.pxl.services.runtime.config.RuntimeSftpProperties;
import be.pxl.services.runtime.domain.ClaimedInterface;
import be.pxl.services.runtime.domain.IncomingInterface;
import be.pxl.services.runtime.exception.InterfacePayloadTooLargeException;
import be.pxl.services.runtime.exception.RuntimeStorageException;

import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.ERROR_DIR;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.ERROR_NOTE_SUFFIX;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.INCOMING_DIR;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.PROCESSED_DIR;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.PROCESSING_DIR;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.buildClaimedFilename;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.buildCollisionFreeName;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.buildErrorNote;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.extractModifyTime;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.extractOriginalFilename;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.isAlreadyExistsError;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.isDirectory;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.isEligibleXmlFile;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.isMissingFileError;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.isSafeSegment;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.isStaleProcessingFile;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.joinPath;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.normalizeRoot;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.shortToken;

/**
 * SFTP-backed implementation of {@link RuntimeInterfaceStorage} using atomic SFTP rename
 * claims for multi-instance safety across Kubernetes replicas.
 *
 * <p>Layout under {@code sftp.runtime.remote-dir}:
 * {@code /Clients/<customer>/<messageType>/{incoming,processing,processed,error}/}
 */
@Service
public class SftpRuntimeInterfaceStorage implements RuntimeInterfaceStorage {

    private static final Logger LOGGER = LoggerFactory.getLogger(SftpRuntimeInterfaceStorage.class);
    private static final String CLAIMED_REQUIRED_MESSAGE = "claimed must not be null";
    private static final Duration MISSING_ROOT_WARN_INTERVAL = Duration.ofSeconds(60);
    private static final Comparator<IncomingInterface> OLDEST_FIRST = Comparator
            .comparing(IncomingInterface::lastModified)
            .thenComparing(IncomingInterface::remotePath);

    private final SftpRemoteFileTemplate sftpTemplate;
    private final String clientsRoot;
    private final long maxFileSizeBytes;
    private final Clock clock;
    private final AtomicReference<Instant> lastMissingRootWarnAt = new AtomicReference<>();

    @Autowired
    public SftpRuntimeInterfaceStorage(
            @Qualifier(RuntimeSftpConfig.RUNTIME_SFTP_TEMPLATE) SftpRemoteFileTemplate sftpTemplate,
            RuntimeSftpProperties sftpProperties,
            Clock clock
    ) {
        this(sftpTemplate, sftpProperties.remoteDir(), sftpProperties.maxFileSizeBytes(), clock);
    }

    SftpRuntimeInterfaceStorage(
            SftpRemoteFileTemplate sftpTemplate,
            String clientsRoot,
            long maxFileSizeBytes,
            Clock clock
    ) {
        this.sftpTemplate = sftpTemplate;
        this.clientsRoot = normalizeRoot(clientsRoot);
        this.maxFileSizeBytes = maxFileSizeBytes > 0
                ? maxFileSizeBytes
                : RuntimeSftpProperties.DEFAULT_MAX_FILE_SIZE_BYTES;
        this.clock = clock;
    }

    @Override
    public List<IncomingInterface> listReadyIncoming(Duration minFileAge) {
        Duration effectiveAge = (minFileAge == null || minFileAge.isNegative()) ? Duration.ZERO : minFileAge;
        Instant cutoff = clock.instant().minus(effectiveAge);
        try {
            List<IncomingInterface> result = sftpTemplate.execute(session -> scanIncoming(session, cutoff));
            return result != null ? result : List.of();
        } catch (Exception ex) {
            throw new RuntimeStorageException("Failed to list incoming interfaces under " + clientsRoot, ex);
        }
    }

    @Override
    public Optional<ClaimedInterface> tryClaim(IncomingInterface candidate, String instanceId) {
        Objects.requireNonNull(candidate, "candidate must not be null");
        String processingDir = joinPath(candidate.baseDir(), PROCESSING_DIR);
        String claimedPath = joinPath(
                processingDir, buildClaimedFilename(candidate.filename(), instanceId, clock.instant()));
        try {
            boolean claimed = Boolean.TRUE.equals(
                    sftpTemplate.execute(session -> {
                        ensureDirectoryExists(session, processingDir);
                        return renameClaimAtomically(session, candidate.remotePath(), claimedPath);
                    }));
            return claimed
                    ? Optional.of(new ClaimedInterface(
                            candidate.customer(), candidate.messageType(), candidate.filename(), candidate.baseDir(), claimedPath))
                    : Optional.empty();
        } catch (Exception ex) {
            throw new RuntimeStorageException("Failed to claim incoming interface " + candidate.remotePath(), ex);
        }
    }

    @Override
    public byte[] readBytes(ClaimedInterface claimed) {
        Objects.requireNonNull(claimed, CLAIMED_REQUIRED_MESSAGE);
        try {
            byte[] bytes = sftpTemplate.execute(session -> {
                verifyRemoteSizeWithinLimit(session, claimed);
                BoundedByteArrayOutputStream output =
                        new BoundedByteArrayOutputStream(maxFileSizeBytes, claimed.filename());
                session.read(claimed.claimedPath(), output);
                return output.toByteArray();
            });
            return bytes != null ? bytes : new byte[0];
        } catch (Exception ex) {
            InterfacePayloadTooLargeException tooLarge = findPayloadTooLarge(ex);
            if (tooLarge != null) {
                throw tooLarge;
            }
            throw new RuntimeStorageException("Failed to read claimed interface " + claimed.claimedPath(), ex);
        }
    }

    @Override
    public void moveToProcessed(ClaimedInterface claimed) {
        Objects.requireNonNull(claimed, CLAIMED_REQUIRED_MESSAGE);
        String processedDir = joinPath(claimed.baseDir(), PROCESSED_DIR);
        try {
            sftpTemplate.execute(session -> {
                ensureDirectoryExists(session, processedDir);
                renameWithoutOverwrite(session, claimed.claimedPath(), processedDir, claimed.filename());
                return null;
            });
        } catch (Exception ex) {
            throw new RuntimeStorageException("Failed to move " + claimed.claimedPath() + " to processed/", ex);
        }
    }

    @Override
    public void moveToError(ClaimedInterface claimed, String reason) {
        Objects.requireNonNull(claimed, CLAIMED_REQUIRED_MESSAGE);
        String errorDir = joinPath(claimed.baseDir(), ERROR_DIR);
        try {
            sftpTemplate.execute(session -> {
                ensureDirectoryExists(session, errorDir);
                Optional<String> destination =
                        renameWithoutOverwrite(session, claimed.claimedPath(), errorDir, claimed.filename());
                destination.ifPresent(dest -> writeErrorNoteBestEffort(session, claimed, reason, dest));
                return null;
            });
        } catch (Exception ex) {
            throw new RuntimeStorageException("Failed to move " + claimed.claimedPath() + " to error/", ex);
        }
    }

    @Override
    public int recoverStaleClaims(Duration maxAge) {
        if (maxAge == null || maxAge.isNegative() || maxAge.isZero()) {
            throw new IllegalArgumentException("maxAge must be positive");
        }
        Instant staleCutoff = clock.instant().minus(maxAge);
        try {
            Integer recovered = sftpTemplate.execute(session -> scanAndRecoverStale(session, staleCutoff));
            return recovered != null ? recovered : 0;
        } catch (Exception ex) {
            throw new RuntimeStorageException("Failed to recover stale claims under " + clientsRoot, ex);
        }
    }

    private List<IncomingInterface> scanIncoming(Session<SftpClient.DirEntry> session, Instant cutoff)
            throws IOException {
        Optional<List<String>> customers = listRootCustomers(session);
        if (customers.isEmpty()) {
            return List.of();
        }
        List<IncomingInterface> ready = new ArrayList<>();
        for (String customer : customers.get()) {
            scanCustomerIncoming(session, customer, cutoff, ready);
        }
        ready.sort(OLDEST_FIRST);
        return ready;
    }

    private void scanCustomerIncoming(
            Session<SftpClient.DirEntry> session,
            String customer,
            Instant cutoff,
            List<IncomingInterface> ready
    ) {
        String customerDir = joinPath(clientsRoot, customer);
        try {
            for (String messageType : listSafeSubdirectories(session, customerDir)) {
                collectIncomingFilesSafely(session, customer, messageType, joinPath(customerDir, messageType), cutoff, ready);
            }
        } catch (IOException ex) {
            LOGGER.warn("Skipping customer directory {} due to SFTP read error: {}", customerDir, ex.getMessage());
        }
    }

    private void collectIncomingFilesSafely(
            Session<SftpClient.DirEntry> session,
            String customer,
            String messageType,
            String baseDir,
            Instant cutoff,
            List<IncomingInterface> ready
    ) {
        String incomingDir = joinPath(baseDir, INCOMING_DIR);
        try {
            for (SftpClient.DirEntry entry : listDirectoryEntries(session, incomingDir)) {
                if (!isEligibleXmlFile(entry, cutoff)) {
                    continue;
                }
                String filename = entry.getFilename();
                Instant modifiedAt = extractModifyTime(entry).orElse(Instant.EPOCH);
                ready.add(new IncomingInterface(
                        customer, messageType, filename, baseDir, joinPath(incomingDir, filename), modifiedAt));
            }
        } catch (IOException ex) {
            LOGGER.warn("Skipping incoming directory {} due to SFTP read error: {}", incomingDir, ex.getMessage());
        }
    }

    private int scanAndRecoverStale(Session<SftpClient.DirEntry> session, Instant staleCutoff) throws IOException {
        Optional<List<String>> customers = listRootCustomers(session);
        if (customers.isEmpty()) {
            return 0;
        }
        int total = 0;
        for (String customer : customers.get()) {
            total += recoverCustomerStale(session, customer, staleCutoff);
        }
        return total;
    }

    private int recoverCustomerStale(Session<SftpClient.DirEntry> session, String customer, Instant staleCutoff) {
        String customerDir = joinPath(clientsRoot, customer);
        int recovered = 0;
        try {
            for (String messageType : listSafeSubdirectories(session, customerDir)) {
                recovered += recoverStaleInBaseDirSafely(session, joinPath(customerDir, messageType), staleCutoff);
            }
        } catch (IOException ex) {
            LOGGER.warn("Skipping stale-claim scan for {} due to SFTP error: {}", customerDir, ex.getMessage());
        }
        return recovered;
    }

    private int recoverStaleInBaseDirSafely(Session<SftpClient.DirEntry> session, String baseDir, Instant staleCutoff) {
        String processingDir = joinPath(baseDir, PROCESSING_DIR);
        String incomingDir = joinPath(baseDir, INCOMING_DIR);
        int recovered = 0;
        try {
            for (SftpClient.DirEntry entry : listDirectoryEntries(session, processingDir)) {
                if (isStaleProcessingFile(entry, staleCutoff)
                        && recoverSingleClaim(session, processingDir, incomingDir, entry)) {
                    recovered++;
                }
            }
        } catch (IOException ex) {
            LOGGER.warn("Skipping stale-claim scan for {} due to SFTP error: {}", processingDir, ex.getMessage());
        }
        return recovered;
    }

    private boolean recoverSingleClaim(
            Session<SftpClient.DirEntry> session,
            String processingDir,
            String incomingDir,
            SftpClient.DirEntry entry
    ) throws IOException {
        String sourcePath = joinPath(processingDir, entry.getFilename());
        String originalFilename = extractOriginalFilename(entry.getFilename());
        if (!isSafeSegment(originalFilename)) {
            LOGGER.warn("Skipping stale claim {} because extracted original filename '{}' is unsafe",
                    sourcePath, originalFilename);
            return false;
        }
        ensureDirectoryExists(session, incomingDir);
        Optional<String> recoveredPath = renameWithoutOverwrite(session, sourcePath, incomingDir, originalFilename);
        if (recoveredPath.isPresent()) {
            LOGGER.warn("Recovered stale claim {} back to {}", sourcePath, recoveredPath.get());
            return true;
        }
        return false;
    }

    /**
     * Renames {@code sourcePath} into {@code targetDir} without ever overwriting an existing file.
     * Uses direct {@link SftpClient#rename(String, String)} (no {@code CopyMode.Overwrite}) when
     * backed by a real SFTP session, falling back to a collision-free name if the target exists.
     */
    private Optional<String> renameWithoutOverwrite(
            Session<SftpClient.DirEntry> session,
            String sourcePath,
            String targetDir,
            String filename
    ) throws IOException {
        String primaryTarget = joinPath(targetDir, filename);
        if (session.getClientInstance() instanceof SftpClient sftpClient) {
            return renameDirectWithoutOverwrite(sftpClient, sourcePath, targetDir, filename, primaryTarget);
        }
        String target = session.exists(primaryTarget)
                ? joinPath(targetDir, buildCollisionFreeName(filename, clock.millis(), shortToken()))
                : primaryTarget;
        return renameClaimAtomically(session, sourcePath, target) ? Optional.of(target) : Optional.empty();
    }

    private Optional<String> renameDirectWithoutOverwrite(
            SftpClient sftpClient,
            String sourcePath,
            String targetDir,
            String filename,
            String primaryTarget
    ) throws IOException {
        try {
            sftpClient.rename(sourcePath, primaryTarget);
            return Optional.of(primaryTarget);
        } catch (IOException ex) {
            if (isMissingFileError(ex)) {
                LOGGER.debug("File {} was already moved by another pod/worker", sourcePath);
                return Optional.empty();
            }
            if (!isAlreadyExistsError(ex)) {
                throw ex;
            }
            String collisionFreeTarget = joinPath(targetDir, buildCollisionFreeName(filename, clock.millis(), shortToken()));
            try {
                sftpClient.rename(sourcePath, collisionFreeTarget);
                return Optional.of(collisionFreeTarget);
            } catch (IOException retryEx) {
                if (isMissingFileError(retryEx)) {
                    LOGGER.debug("File {} was already moved by another pod/worker", sourcePath);
                    return Optional.empty();
                }
                throw retryEx;
            }
        }
    }

    private boolean renameClaimAtomically(Session<SftpClient.DirEntry> session, String sourcePath, String targetPath)
            throws IOException {
        try {
            if (session.getClientInstance() instanceof SftpClient sftpClient) {
                sftpClient.rename(sourcePath, targetPath);
            } else {
                session.rename(sourcePath, targetPath);
            }
            return true;
        } catch (IOException ex) {
            if (isMissingFileError(ex)) {
                LOGGER.debug("File {} was already moved by another pod/worker", sourcePath);
                return false;
            }
            throw ex;
        }
    }

    private void verifyRemoteSizeWithinLimit(Session<SftpClient.DirEntry> session, ClaimedInterface claimed)
            throws IOException {
        if (session.getClientInstance() instanceof SftpClient sftpClient) {
            SftpClient.Attributes attrs = sftpClient.stat(claimed.claimedPath());
            if (attrs != null && attrs.getSize() > maxFileSizeBytes) {
                throw payloadTooLarge(claimed.filename(), maxFileSizeBytes);
            }
        }
    }

    private void writeErrorNoteBestEffort(
            Session<SftpClient.DirEntry> session,
            ClaimedInterface claimed,
            String reason,
            String destination
    ) {
        try {
            byte[] noteBytes = buildErrorNote(claimed, reason, clock.instant()).getBytes(StandardCharsets.UTF_8);
            session.write(new ByteArrayInputStream(noteBytes), destination + ERROR_NOTE_SUFFIX);
        } catch (IOException noteEx) {
            LOGGER.warn("Moved {} to {} in error/, but failed to write companion error note: {}",
                    claimed.claimedPath(), destination, noteEx.getMessage());
        }
    }

    private Optional<List<String>> listRootCustomers(Session<SftpClient.DirEntry> session) throws IOException {
        try {
            return Optional.of(listSafeSubdirectories(session, clientsRoot));
        } catch (IOException ex) {
            if (isMissingFileError(ex)) {
                warnMissingClientsRootThrottled();
                return Optional.empty();
            }
            throw ex;
        }
    }

    private void warnMissingClientsRootThrottled() {
        Instant now = clock.instant();
        Instant lastWarn = lastMissingRootWarnAt.get();
        if ((lastWarn == null || !now.isBefore(lastWarn.plus(MISSING_ROOT_WARN_INTERVAL)))
                && lastMissingRootWarnAt.compareAndSet(lastWarn, now)) {
            LOGGER.warn("Configured SFTP clients root '{}' does not exist on sftp-runtime; "
                    + "verify SFTP_RUNTIME_REMOTE_DIR", clientsRoot);
        }
    }

    private SftpClient.DirEntry[] listDirectoryEntries(Session<SftpClient.DirEntry> session, String dirPath)
            throws IOException {
        try {
            SftpClient.DirEntry[] entries = session.list(dirPath);
            return entries != null ? entries : new SftpClient.DirEntry[0];
        } catch (IOException ex) {
            if (isMissingFileError(ex)) {
                return new SftpClient.DirEntry[0];
            }
            throw ex;
        }
    }

    private List<String> listSafeSubdirectories(Session<SftpClient.DirEntry> session, String parentDir)
            throws IOException {
        SftpClient.DirEntry[] entries = session.list(parentDir);
        if (entries == null) {
            return List.of();
        }
        List<String> names = new ArrayList<>();
        for (SftpClient.DirEntry entry : entries) {
            String name = entry.getFilename();
            if (isDirectory(entry) && isSafeSegment(name)) {
                names.add(name);
            }
        }
        names.sort(String.CASE_INSENSITIVE_ORDER);
        return names;
    }

    private void ensureDirectoryExists(Session<SftpClient.DirEntry> session, String dirPath) throws IOException {
        if (session.exists(dirPath)) {
            return;
        }
        try {
            session.mkdir(dirPath);
        } catch (IOException ex) {
            if (!session.exists(dirPath)) {
                throw ex;
            }
        }
    }

    private static InterfacePayloadTooLargeException payloadTooLarge(String filename, long maxBytes) {
        return new InterfacePayloadTooLargeException(
                "Interface file '" + filename + "' exceeds maximum allowed size of " + maxBytes + " bytes");
    }

    private static InterfacePayloadTooLargeException findPayloadTooLarge(Throwable error) {
        Throwable current = error;
        while (current != null) {
            if (current instanceof InterfacePayloadTooLargeException tooLarge) {
                return tooLarge;
            }
            current = current.getCause();
        }
        return null;
    }

    /**
     * In-memory stream that enforces {@code maxBytes} before buffering to prevent OOM crash loops.
     */
    private static final class BoundedByteArrayOutputStream extends OutputStream {

        private final ByteArrayOutputStream delegate = new ByteArrayOutputStream();
        private final long maxBytes;
        private final String filename;
        private long written;

        BoundedByteArrayOutputStream(long maxBytes, String filename) {
            this.maxBytes = maxBytes;
            this.filename = filename;
        }

        @Override
        public void write(int b) {
            checkLimit(1);
            delegate.write(b);
            written++;
        }

        @Override
        public void write(byte[] b, int off, int len) {
            Objects.checkFromIndexSize(off, len, b.length);
            checkLimit(len);
            delegate.write(b, off, len);
            written += len;
        }

        byte[] toByteArray() {
            return delegate.toByteArray();
        }

        private void checkLimit(int incomingBytes) {
            if (incomingBytes > maxBytes - written) {
                throw payloadTooLarge(filename, maxBytes);
            }
        }
    }
}
