package be.pxl.services.runtime.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Configuration properties for connecting to the {@code sftp-shared} server with the mapping packages.
 * This is a different server than {@code sftp-runtime} with the customer interfaces ({@code sftp.runtime.*}).
 * Credentials are supplied exclusively via environment variables or secrets.
 */
@ConfigurationProperties(prefix = "sftp.shared")
public record SharedSftpProperties(
        String host,
        int port,
        String user,
        String password,
        String packagesPath,
        boolean allowUnknownKeys
) {
    public static final String DEFAULT_HOST = "localhost";
    public static final int DEFAULT_PORT = 2222;
    public static final String DEFAULT_USER = "shareduser";
    public static final String DEFAULT_PACKAGES_PATH = "/Packages";

    public SharedSftpProperties {
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
        if (packagesPath == null || packagesPath.isBlank()) {
            packagesPath = DEFAULT_PACKAGES_PATH;
        }
    }
}
