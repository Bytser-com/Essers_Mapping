package be.pxl.services.runtime.storage;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.NoSuchFileException;
import java.nio.file.attribute.FileTime;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.UUID;

import org.apache.sshd.sftp.client.SftpClient;
import org.apache.sshd.sftp.common.SftpConstants;
import org.apache.sshd.sftp.common.SftpException;
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

/**
 * SFTP-backed implementation of {@link RuntimeInterfaceStorage} using atomic SFTP rename
 * claims for multi-instance safety across Kubernetes replicas.
 *
 * <p>Directory layout under {@code sftp.runtime.remote-dir} (default {@code /Clients}):
 * <pre>
 * /Clients/&lt;customer&gt;/&lt;messageType&gt;/
 * ├── incoming/    &lt;-- customer uploads .xml interfaces here
 * ├── processing/  &lt;-- claimed atomically by a single runtime pod
 * ├── processed/   &lt;-- successfully handled interfaces
 * └── error/       &lt;-- failed interfaces + readable .error.txt
 * </pre>
 */
@Service
public class SftpRuntimeInterfaceStorage implements RuntimeInterfaceStorage {

    private static final Logger LOGGER = LoggerFactory.getLogger(SftpRuntimeInterfaceStorage.class);

    static final String INCOMING_DIR = "incoming";
    static final String PROCESSING_DIR = "processing";
    static final String PROCESSED_DIR = "processed";
    static final String ERROR_DIR = "error";
    static final String PROCESSING_SUFFIX = ".processing";
    private static final String XML_EXTENSION = ".xml";
    private static final String ERROR_NOTE_SUFFIX = ".error.txt";

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
            List<IncomingInterface> result = sftpTemplate.execute(session -> {
                if (!session.exists(clientsRoot)) {
                    return List.<IncomingInterface>of();
                }
                List<IncomingInterface> ready = new ArrayList<>();
                for (String customer : listSafeSubdirectories(session, clientsRoot)) {
                    String customerDir = joinPath(clientsRoot, customer);
                    for (String messageType : listSafeSubdirectories(session, customerDir)) {
                        String baseDir = joinPath(customerDir, messageType);
                        collectIncomingFiles(session, customer, messageType, baseDir, cutoff, ready);
                    }
                }
                ready.sort(OLDEST_FIRST);
                return ready;
            });
            return result != null ? result : List.of();
        } catch (Exception ex) {
            throw new RuntimeStorageException(
                    "Failed to list incoming customer interfaces under " + clientsRoot, ex);
        }
    }

    @Override
    public Optional<ClaimedInterface> tryClaim(IncomingInterface candidate, String instanceId) {
        if (candidate == null) {
            throw new IllegalArgumentException("candidate must not be null");
        }
        String safeInstance = sanitizeInstanceId(instanceId);
        String processingDir = joinPath(candidate.baseDir(), PROCESSING_DIR);
        String claimToken = UUID.randomUUID().toString().substring(0, 8);
        String claimedFilename = candidate.filename() + "." + safeInstance + "." + claimToken + PROCESSING_SUFFIX;
        String claimedPath = joinPath(processingDir, claimedFilename);

        try {
            Boolean claimed = sftpTemplate.execute(session -> {
                ensureDirectoryExists(session, processingDir);
                try {
                    session.rename(candidate.remotePath(), claimedPath);
                    return Boolean.TRUE;
                } catch (IOException ex) {
                    if (isMissingFileError(ex)) {
                        LOGGER.debug("Interface {} was already claimed by another pod/worker",
                                candidate.remotePath());
                        return Boolean.FALSE;
                    }
                    throw ex;
                }
            });
            if (Boolean.TRUE.equals(claimed)) {
                return Optional.of(new ClaimedInterface(
                        candidate.customer(),
                        candidate.messageType(),
                        candidate.filename(),
                        candidate.baseDir(),
                        claimedPath
                ));
            }
            return Optional.empty();
        } catch (Exception ex) {
            if (isMissingFileError(ex)) {
                LOGGER.debug("Interface {} was already claimed by another pod/worker", candidate.remotePath());
                return Optional.empty();
            }
            throw new RuntimeStorageException(
                    "Failed to claim incoming interface " + candidate.remotePath(), ex);
        }
    }

    @Override
    public byte[] readBytes(ClaimedInterface claimed) {
        if (claimed == null) {
            throw new IllegalArgumentException("claimed must not be null");
        }
        try {
            byte[] bytes = sftpTemplate.execute(session -> {
                ByteArrayOutputStream output = new ByteArrayOutputStream();
                session.read(claimed.claimedPath(), output);
                return output.toByteArray();
            });
            return bytes != null ? bytes : new byte[0];
        } catch (Exception ex) {
            throw new RuntimeStorageException(
                    "Failed to read claimed interface " + claimed.claimedPath(), ex);
        }
    }

    @Override
    public void moveToProcessed(ClaimedInterface claimed) {
        if (claimed == null) {
            throw new IllegalArgumentException("claimed must not be null");
        }
        String processedDir = joinPath(claimed.baseDir(), PROCESSED_DIR);
        try {
            sftpTemplate.execute(session -> {
                ensureDirectoryExists(session, processedDir);
                String destination = resolveUniqueDestination(session, processedDir, claimed.filename());
                session.rename(claimed.claimedPath(), destination);
                return null;
            });
        } catch (Exception ex) {
            throw new RuntimeStorageException(
                    "Failed to move claimed interface " + claimed.claimedPath() + " to processed/", ex);
        }
    }

    @Override
    public void moveToError(ClaimedInterface claimed, String reason) {
        if (claimed == null) {
            throw new IllegalArgumentException("claimed must not be null");
        }
        String errorDir = joinPath(claimed.baseDir(), ERROR_DIR);
        String sanitizedReason = (reason == null || reason.isBlank()) ? "Unknown processing error" : reason.trim();

        try {
            sftpTemplate.execute(session -> {
                ensureDirectoryExists(session, errorDir);
                String destination = resolveUniqueDestination(session, errorDir, claimed.filename());
                session.rename(claimed.claimedPath(), destination);

                String noteContent = buildErrorNote(claimed, sanitizedReason);
                byte[] noteBytes = noteContent.getBytes(StandardCharsets.UTF_8);
                session.write(new ByteArrayInputStream(noteBytes), destination + ERROR_NOTE_SUFFIX);
                return null;
            });
        } catch (Exception ex) {
            throw new RuntimeStorageException(
                    "Failed to move claimed interface " + claimed.claimedPath() + " to error/", ex);
        }
    }

    @Override
    public int recoverStaleClaims(Duration maxAge) {
        if (maxAge == null || maxAge.isNegative() || maxAge.isZero()) {
            throw new IllegalArgumentException("maxAge must be positive");
        }
        Instant staleCutoff = clock.instant().minus(maxAge);

        try {
            Integer recovered = sftpTemplate.execute(session -> {
                if (!session.exists(clientsRoot)) {
                    return 0;
                }
                int count = 0;
                for (String customer : listSafeSubdirectories(session, clientsRoot)) {
                    String customerDir = joinPath(clientsRoot, customer);
                    for (String messageType : listSafeSubdirectories(session, customerDir)) {
                        String baseDir = joinPath(customerDir, messageType);
                        count += recoverStaleClaimsInBaseDir(session, baseDir, staleCutoff);
                    }
                }
                return count;
            });
            return recovered != null ? recovered : 0;
        } catch (Exception ex) {
            throw new RuntimeStorageException(
                    "Failed to recover stale processing claims under " + clientsRoot, ex);
        }
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
        if (!session.exists(incomingDir)) {
            return;
        }
        SftpClient.DirEntry[] entries = session.list(incomingDir);
        if (entries == null) {
            return;
        }
        for (SftpClient.DirEntry entry : entries) {
            if (isDirectory(entry)) {
                continue;
            }
            String filename = entry.getFilename();
            if (!isEligibleXmlFilename(filename)) {
                continue;
            }
            Instant modifiedAt = extractModifyTime(entry);
            if (modifiedAt.isAfter(cutoff)) {
                continue;
            }
            ready.add(new IncomingInterface(
                    customer,
                    messageType,
                    filename,
                    baseDir,
                    joinPath(incomingDir, filename),
                    modifiedAt
            ));
        }
    }

    private int recoverStaleClaimsInBaseDir(
            Session<SftpClient.DirEntry> session,
            String baseDir,
            Instant staleCutoff
    ) throws IOException {
        String processingDir = joinPath(baseDir, PROCESSING_DIR);
        if (!session.exists(processingDir)) {
            return 0;
        }
        SftpClient.DirEntry[] entries = session.list(processingDir);
        if (entries == null) {
            return 0;
        }
        String incomingDir = joinPath(baseDir, INCOMING_DIR);
        int recovered = 0;
        for (SftpClient.DirEntry entry : entries) {
            if (isDirectory(entry)) {
                continue;
            }
            String filename = entry.getFilename();
            if (!isSafeSegment(filename) || !filename.endsWith(PROCESSING_SUFFIX)) {
                continue;
            }
            Instant modifiedAt = extractModifyTime(entry);
            if (modifiedAt.isAfter(staleCutoff)) {
                continue;
            }
            String originalFilename = extractOriginalFilename(filename);
            ensureDirectoryExists(session, incomingDir);
            String sourcePath = joinPath(processingDir, filename);
            String targetPath = resolveUniqueDestination(session, incomingDir, originalFilename);
            try {
                session.rename(sourcePath, targetPath);
                recovered++;
                LOGGER.warn("Recovered stale claim {} back to {}", sourcePath, targetPath);
            } catch (IOException ex) {
                if (isMissingFileError(ex)) {
                    LOGGER.debug("Stale claim {} already recovered by another pod", sourcePath);
                } else {
                    throw ex;
                }
            }
        }
        return recovered;
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
            // Concurrent pod may have created the directory at the exact same moment.
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
        String suffix = "_" + clock.millis();
        int dotIndex = filename.lastIndexOf('.');
        String uniqueName = dotIndex > 0
                ? filename.substring(0, dotIndex) + suffix + filename.substring(dotIndex)
                : filename + suffix;
        return joinPath(targetDir, uniqueName);
    }

    private String buildErrorNote(ClaimedInterface claimed, String reason) {
        return "timestamp=" + clock.instant() + System.lineSeparator()
                + "customer=" + claimed.customer() + System.lineSeparator()
                + "messageType=" + claimed.messageType() + System.lineSeparator()
                + "filename=" + claimed.filename() + System.lineSeparator()
                + "reason=" + reason + System.lineSeparator();
    }

    static String extractOriginalFilename(String claimedFilename) {
        String withoutSuffix = claimedFilename.endsWith(PROCESSING_SUFFIX)
                ? claimedFilename.substring(0, claimedFilename.length() - PROCESSING_SUFFIX.length())
                : claimedFilename;
        int xmlEnd = withoutSuffix.toLowerCase(Locale.ROOT).lastIndexOf(XML_EXTENSION);
        if (xmlEnd > 0) {
            return withoutSuffix.substring(0, xmlEnd + XML_EXTENSION.length());
        }
        return withoutSuffix;
    }

    private static boolean isEligibleXmlFilename(String filename) {
        if (!isSafeSegment(filename)) {
            return false;
        }
        return filename.toLowerCase(Locale.ROOT).endsWith(XML_EXTENSION);
    }

    private static boolean isSafeSegment(String segment) {
        if (segment == null || segment.isBlank()) {
            return false;
        }
        return !".".equals(segment)
                && !"..".equals(segment)
                && !segment.contains("/")
                && !segment.contains("\\")
                && !segment.contains("..");
    }

    private static boolean isDirectory(SftpClient.DirEntry entry) {
        if (entry == null || entry.getAttributes() == null) {
            return false;
        }
        return entry.getAttributes().isDirectory()
                || entry.getAttributes().getType() == SftpConstants.SSH_FILEXFER_TYPE_DIRECTORY;
    }

    private Instant extractModifyTime(SftpClient.DirEntry entry) {
        if (entry.getAttributes() != null) {
            FileTime modifyTime = entry.getAttributes().getModifyTime();
            if (modifyTime != null) {
                return modifyTime.toInstant();
            }
        }
        return Instant.EPOCH;
    }

    private static boolean isMissingFileError(Throwable error) {
        Throwable current = error;
        while (current != null) {
            if (current instanceof NoSuchFileException) {
                return true;
            }
            if (current instanceof SftpException sftpEx
                    && sftpEx.getStatus() == SftpConstants.SSH_FX_NO_SUCH_FILE) {
                return true;
            }
            String message = current.getMessage();
            if (message != null && message.toLowerCase(Locale.ROOT).contains("no such file")) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private static String normalizeRoot(String root) {
        if (root == null || root.isBlank() || "/".equals(root.trim())) {
            return "/";
        }
        String trimmed = root.trim();
        while (trimmed.endsWith("/") && trimmed.length() > 1) {
            trimmed = trimmed.substring(0, trimmed.length() - 1);
        }
        return trimmed;
    }

    private static String joinPath(String parent, String child) {
        if ("/".equals(parent)) {
            return "/" + child;
        }
        return parent + "/" + child;
    }

    private static String sanitizeInstanceId(String instanceId) {
        String cleaned = instanceId == null ? "" : instanceId.trim().replaceAll("[^A-Za-z0-9._-]", "");
        if (cleaned.isEmpty()) {
            throw new IllegalArgumentException("instanceId must not be blank");
        }
        return cleaned;
    }
}
