package be.pxl.services.runtime.storage;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

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
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.isDirectory;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.isEligibleXmlFile;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.isMissingFileError;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.isSafeSegment;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.isStaleProcessingFile;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.joinPath;
import static be.pxl.services.runtime.storage.SftpInterfacePathSupport.normalizeRoot;

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
    private static final Comparator<IncomingInterface> OLDEST_FIRST = Comparator
            .comparing(IncomingInterface::lastModified)
            .thenComparing(IncomingInterface::remotePath);

    private final SftpRemoteFileTemplate sftpTemplate;
    private final String clientsRoot;
    private final Clock clock;

    @Autowired
    public SftpRuntimeInterfaceStorage(
            @Qualifier(RuntimeSftpConfig.RUNTIME_SFTP_TEMPLATE) SftpRemoteFileTemplate sftpTemplate,
            RuntimeSftpProperties sftpProperties
    ) {
        this(sftpTemplate, sftpProperties.remoteDir(), Clock.systemUTC());
    }

    SftpRuntimeInterfaceStorage(SftpRemoteFileTemplate sftpTemplate, String clientsRoot, Clock clock) {
        this.sftpTemplate = sftpTemplate;
        this.clientsRoot = normalizeRoot(clientsRoot);
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
        String claimedPath = joinPath(processingDir, buildClaimedFilename(candidate.filename(), instanceId));
        try {
            boolean claimed = Boolean.TRUE.equals(
                    sftpTemplate.execute(session -> renameAtomically(session, processingDir, candidate.remotePath(), claimedPath)));
            return claimed
                    ? Optional.of(new ClaimedInterface(
                            candidate.customer(), candidate.messageType(), candidate.filename(), candidate.baseDir(), claimedPath))
                    : Optional.empty();
        } catch (Exception ex) {
            if (isMissingFileError(ex)) {
                LOGGER.debug("Interface {} was already claimed by another pod/worker", candidate.remotePath());
                return Optional.empty();
            }
            throw new RuntimeStorageException("Failed to claim incoming interface " + candidate.remotePath(), ex);
        }
    }

    @Override
    public byte[] readBytes(ClaimedInterface claimed) {
        Objects.requireNonNull(claimed, CLAIMED_REQUIRED_MESSAGE);
        try {
            byte[] bytes = sftpTemplate.execute(session -> {
                ByteArrayOutputStream output = new ByteArrayOutputStream();
                session.read(claimed.claimedPath(), output);
                return output.toByteArray();
            });
            return bytes != null ? bytes : new byte[0];
        } catch (Exception ex) {
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
                session.rename(claimed.claimedPath(), resolveUniqueDestination(session, processedDir, claimed.filename()));
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
                String destination = resolveUniqueDestination(session, errorDir, claimed.filename());
                session.rename(claimed.claimedPath(), destination);
                byte[] noteBytes = buildErrorNote(claimed, reason, clock.instant()).getBytes(StandardCharsets.UTF_8);
                session.write(new ByteArrayInputStream(noteBytes), destination + ERROR_NOTE_SUFFIX);
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
        if (!session.exists(clientsRoot)) {
            return List.of();
        }
        List<IncomingInterface> ready = new ArrayList<>();
        for (String customer : listSafeSubdirectories(session, clientsRoot)) {
            String customerDir = joinPath(clientsRoot, customer);
            for (String messageType : listSafeSubdirectories(session, customerDir)) {
                collectIncomingFiles(session, customer, messageType, joinPath(customerDir, messageType), cutoff, ready);
            }
        }
        ready.sort(OLDEST_FIRST);
        return ready;
    }

    private void collectIncomingFiles(
            Session<SftpClient.DirEntry> session,
            String customer,
            String messageType,
            String baseDir,
            Instant cutoff,
            List<IncomingInterface> ready
    ) throws IOException {
        String incomingDir = joinPath(baseDir, INCOMING_DIR);
        for (SftpClient.DirEntry entry : listDirectoryEntries(session, incomingDir)) {
            if (!isEligibleXmlFile(entry, cutoff)) {
                continue;
            }
            String filename = entry.getFilename();
            ready.add(new IncomingInterface(
                    customer, messageType, filename, baseDir, joinPath(incomingDir, filename), extractModifyTime(entry)));
        }
    }

    private int scanAndRecoverStale(Session<SftpClient.DirEntry> session, Instant staleCutoff) throws IOException {
        if (!session.exists(clientsRoot)) {
            return 0;
        }
        int total = 0;
        for (String customer : listSafeSubdirectories(session, clientsRoot)) {
            String customerDir = joinPath(clientsRoot, customer);
            for (String messageType : listSafeSubdirectories(session, customerDir)) {
                total += recoverStaleInBaseDir(session, joinPath(customerDir, messageType), staleCutoff);
            }
        }
        return total;
    }

    private int recoverStaleInBaseDir(Session<SftpClient.DirEntry> session, String baseDir, Instant staleCutoff)
            throws IOException {
        String processingDir = joinPath(baseDir, PROCESSING_DIR);
        String incomingDir = joinPath(baseDir, INCOMING_DIR);
        int recovered = 0;
        for (SftpClient.DirEntry entry : listDirectoryEntries(session, processingDir)) {
            if (isStaleProcessingFile(entry, staleCutoff) && recoverSingleClaim(session, processingDir, incomingDir, entry)) {
                recovered++;
            }
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
        ensureDirectoryExists(session, incomingDir);
        String targetPath = resolveUniqueDestination(session, incomingDir, originalFilename);
        if (renameAtomically(session, incomingDir, sourcePath, targetPath)) {
            LOGGER.warn("Recovered stale claim {} back to {}", sourcePath, targetPath);
            return true;
        }
        return false;
    }

    private boolean renameAtomically(
            Session<SftpClient.DirEntry> session,
            String targetDir,
            String sourcePath,
            String targetPath
    ) throws IOException {
        ensureDirectoryExists(session, targetDir);
        try {
            session.rename(sourcePath, targetPath);
            return true;
        } catch (IOException ex) {
            if (isMissingFileError(ex)) {
                LOGGER.debug("File {} was already moved by another pod/worker", sourcePath);
                return false;
            }
            throw ex;
        }
    }

    private SftpClient.DirEntry[] listDirectoryEntries(Session<SftpClient.DirEntry> session, String dirPath)
            throws IOException {
        if (!session.exists(dirPath)) {
            return new SftpClient.DirEntry[0];
        }
        SftpClient.DirEntry[] entries = session.list(dirPath);
        return entries != null ? entries : new SftpClient.DirEntry[0];
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

    private String resolveUniqueDestination(
            Session<SftpClient.DirEntry> session,
            String targetDir,
            String filename
    ) throws IOException {
        String candidate = joinPath(targetDir, filename);
        if (!session.exists(candidate)) {
            return candidate;
        }
        return joinPath(targetDir, buildCollisionFreeName(filename, clock.millis()));
    }
}
