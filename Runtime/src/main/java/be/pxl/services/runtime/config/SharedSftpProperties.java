package be.pxl.services.runtime.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Configuration properties for connecting to the {@code sftp-shared} server with the mapping packages.
 * This is a different server than {@code sftp-runtime} with the customer interfaces ({@code sftp.runtime.*}).
 */
@ConfigurationProperties(prefix = "sftp.shared")
public record SharedSftpProperties(
        String host,
        int port,
        String user,
        String password,
        String packagesPath,
        boolean allowUnknownKeys,
        int timeoutMs,
        int poolSize
) {
    public static final String DEFAULT_HOST = "localhost";
    public static final int DEFAULT_PORT = 2222;
    public static final String DEFAULT_USER = "shareduser";
    public static final String DEFAULT_PACKAGES_PATH = "/Packages";
    public static final int DEFAULT_TIMEOUT_MS = 10_000;
    public static final int DEFAULT_POOL_SIZE = 10;

    public SharedSftpProperties {
        if (host == null || host.isBlank()) {
            host = DEFAULT_HOST;
        }
        if (port <= 0 || port > 65_535) {
            port = DEFAULT_PORT;
        }
        if (user == null || user.isBlank()) {
            user = DEFAULT_USER;
        }
        if (password == null) {
            password = "";
        }
        if (packagesPath == null || packagesPath.isBlank()) {
            packagesPath = DEFAULT_PACKAGES_PATH;
        }
        if (timeoutMs <= 0) {
            timeoutMs = DEFAULT_TIMEOUT_MS;
        }
        if (poolSize <= 0) {
            poolSize = DEFAULT_POOL_SIZE;
        }
    }

    // Never print the password, also not when the properties end up in a log
    @Override
    public String toString() {
        return "SharedSftpProperties[host=" + host + ", port=" + port + ", user=" + user
                + ", password=****, packagesPath=" + packagesPath + ", allowUnknownKeys=" + allowUnknownKeys
                + ", timeoutMs=" + timeoutMs + ", poolSize=" + poolSize + "]";
    }
}
