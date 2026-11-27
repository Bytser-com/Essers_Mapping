package be.pxl.services.runtime.config;

import org.apache.sshd.sftp.client.SftpClient;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.file.remote.session.CachingSessionFactory;
import org.springframework.integration.file.remote.session.SessionFactory;
import org.springframework.integration.sftp.session.DefaultSftpSessionFactory;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;

/**
 * Infrastructure beans for SFTP access to {@code sftp-shared} (mapping packages).
 * The beans have their own names, so they can live next to the {@code sftp-runtime} beans.
 */
@Configuration
@EnableConfigurationProperties(SharedSftpProperties.class)
public class SharedSftpConfig {

    public static final String SHARED_SFTP_SESSION_FACTORY = "sharedSftpSessionFactory";
    public static final String SHARED_SFTP_TEMPLATE = "sharedSftpTemplate";

    @Bean(name = SHARED_SFTP_SESSION_FACTORY)
    public SessionFactory<SftpClient.DirEntry> sharedSftpSessionFactory(SharedSftpProperties sftpProperties) {
        DefaultSftpSessionFactory factory = new DefaultSftpSessionFactory(true);
        factory.setHost(sftpProperties.host());
        factory.setPort(sftpProperties.port());
        factory.setUser(sftpProperties.user());
        if (!sftpProperties.password().isEmpty()) {
            factory.setPassword(sftpProperties.password());
        }
        factory.setAllowUnknownKeys(sftpProperties.allowUnknownKeys());
        // Reuse SFTP sessions; the first connection is only made on the first request,
        // so the application also starts when the SFTP server is not reachable yet.
        return new CachingSessionFactory<>(factory);
    }

    @Bean(name = SHARED_SFTP_TEMPLATE)
    public SftpRemoteFileTemplate sharedSftpTemplate(
            @Qualifier(SHARED_SFTP_SESSION_FACTORY) SessionFactory<SftpClient.DirEntry> sessionFactory
    ) {
        return new SftpRemoteFileTemplate(sessionFactory);
    }
}
