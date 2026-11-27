package be.pxl.services.runtime.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Configuration properties for connecting to the {@code sftp-runtime} server.
 * Credentials are supplied exclusively via environment variables or secrets.
 */
@ConfigurationProperties(prefix = "sftp.runtime")
public record RuntimeSftpProperties(
        String host,
        int port,
        String user,
        String password,
        String privateKey,
        String privateKeyPassphrase,
        String remoteDir,
        boolean allowUnknownKeys,
        long sessionWaitTimeoutMs
) {
    public static final String DEFAULT_HOST = "localhost";
    public static final int DEFAULT_PORT = 2223;
    public static final String DEFAULT_USER = "runtimeuser";
    public static final String DEFAULT_REMOTE_DIR = "/Clients";
    public static final long DEFAULT_SESSION_WAIT_TIMEOUT_MS = 10_000L;

    public RuntimeSftpProperties {
        if (host == null || host.isBlank()) {
            host = DEFAULT_HOST;
        }
        if (port <= 0) {
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
            sessionWaitTimeoutMs = DEFAULT_SESSION_WAIT_TIMEOUT_MS;
        }
    }
}
