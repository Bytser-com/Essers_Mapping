package be.pxl.services.runtime.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Configuration properties for connecting to the {@code sftp-runtime} server.
 * Credentials are supplied exclusively via environment variables or secrets and
 * are always redacted in {@link #toString()}.
 */
@ConfigurationProperties(prefix = "sftp.runtime")
public record RuntimeSftpProperties(
        String host,
        int port,
        String user,
        String password,
        String privateKey,
        String privateKeyPassphrase,
        String knownHosts,
        String remoteDir,
        boolean allowUnknownKeys,
        long sessionWaitTimeoutMs,
        int connectTimeoutMs,
        long maxFileSizeBytes
) {
    private static final Logger LOGGER = LoggerFactory.getLogger(RuntimeSftpProperties.class);

    public static final String DEFAULT_HOST = "localhost";
    public static final int DEFAULT_PORT = 2223;
    public static final int MAX_PORT = 65_535;
    public static final String DEFAULT_USER = "runtimeuser";
    public static final String DEFAULT_REMOTE_DIR = "/Clients";
    public static final long DEFAULT_SESSION_WAIT_TIMEOUT_MS = 10_000L;
    public static final int DEFAULT_CONNECT_TIMEOUT_MS = 10_000;
    public static final long DEFAULT_MAX_FILE_SIZE_BYTES = 26_214_400L; // 25 MiB

    public RuntimeSftpProperties {
        if (host == null || host.isBlank()) {
            host = DEFAULT_HOST;
        }
        if (port <= 0 || port > MAX_PORT) {
            LOGGER.warn("Invalid sftp.runtime.port={} (expected 1..{}); falling back to {}",
                    port, MAX_PORT, DEFAULT_PORT);
            port = DEFAULT_PORT;
        }
        if (user == null || user.isBlank()) {
            user = DEFAULT_USER;
        }
        if (password == null) {
            password = "";
        }
        if (remoteDir == null || remoteDir.isBlank()) {
            remoteDir = DEFAULT_REMOTE_DIR;
        }
        if (sessionWaitTimeoutMs <= 0) {
            LOGGER.warn("Invalid sftp.runtime.session-wait-timeout-ms={}; falling back to {}",
                    sessionWaitTimeoutMs, DEFAULT_SESSION_WAIT_TIMEOUT_MS);
            sessionWaitTimeoutMs = DEFAULT_SESSION_WAIT_TIMEOUT_MS;
        }
        if (connectTimeoutMs <= 0) {
            LOGGER.warn("Invalid sftp.runtime.connect-timeout-ms={}; falling back to {}",
                    connectTimeoutMs, DEFAULT_CONNECT_TIMEOUT_MS);
            connectTimeoutMs = DEFAULT_CONNECT_TIMEOUT_MS;
        }
        if (maxFileSizeBytes <= 0) {
            LOGGER.warn("Invalid sftp.runtime.max-file-size-bytes={}; falling back to {}",
                    maxFileSizeBytes, DEFAULT_MAX_FILE_SIZE_BYTES);
            maxFileSizeBytes = DEFAULT_MAX_FILE_SIZE_BYTES;
        }
    }

    @Override
    public String toString() {
        return "RuntimeSftpProperties[host=" + host
                + ", port=" + port
                + ", user=" + user
                + ", password=****"
                + ", privateKey=" + (privateKey == null || privateKey.isBlank() ? "" : "<configured>")
                + ", privateKeyPassphrase=****"
                + ", knownHosts=" + (knownHosts == null ? "" : knownHosts)
                + ", remoteDir=" + remoteDir
                + ", allowUnknownKeys=" + allowUnknownKeys
                + ", sessionWaitTimeoutMs=" + sessionWaitTimeoutMs
                + ", connectTimeoutMs=" + connectTimeoutMs
                + ", maxFileSizeBytes=" + maxFileSizeBytes
                + "]";
    }
}
