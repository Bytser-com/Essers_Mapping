package be.essers.services.versioncontrol.infrastructure.sftp;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "sftp")
public record SftpProperties(
        String host,
        int port,
        String user,
        String password,
        String privateKey,
        String privateKeyPassphrase,
        String basePath,
        boolean allowUnknownKeys
) {
    public SftpProperties {
        if (host == null || host.isBlank()) {
            host = "localhost";
        }
        if (port <= 0) {
            port = 22;
        }
        if (user == null || user.isBlank()) {
            user = "sftpuser";
        }
        if (password == null) {
            password = "";
        }
        if (basePath == null || basePath.isBlank()) {
            basePath = "/Proposals";
        }
    }
}
