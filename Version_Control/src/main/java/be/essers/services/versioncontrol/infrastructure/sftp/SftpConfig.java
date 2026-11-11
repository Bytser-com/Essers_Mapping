package be.essers.services.versioncontrol.infrastructure.sftp;

import org.apache.sshd.sftp.client.SftpClient;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ResourceLoader;
import org.springframework.integration.file.remote.session.CachingSessionFactory;
import org.springframework.integration.file.remote.session.SessionFactory;
import org.springframework.integration.sftp.session.DefaultSftpSessionFactory;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;

@Configuration
@EnableConfigurationProperties(SftpProperties.class)
public class SftpConfig {

    @Bean
    public SessionFactory<SftpClient.DirEntry> sftpSessionFactory(SftpProperties properties, ResourceLoader resourceLoader) {
        DefaultSftpSessionFactory factory = new DefaultSftpSessionFactory(true);
        factory.setHost(properties.host());
        factory.setPort(properties.port());
        factory.setUser(properties.user());
        if (properties.password() != null && !properties.password().isEmpty()) {
            factory.setPassword(properties.password());
        }
        if (properties.privateKey() != null && !properties.privateKey().isBlank()) {
            factory.setPrivateKey(resourceLoader.getResource(properties.privateKey()));
            if (properties.privateKeyPassphrase() != null) {
                factory.setPrivateKeyPassphrase(properties.privateKeyPassphrase());
            }
        }
        factory.setAllowUnknownKeys(properties.allowUnknownKeys());
        return new CachingSessionFactory<>(factory);
    }

    @Bean
    public SftpRemoteFileTemplate sftpRemoteFileTemplate(SessionFactory<SftpClient.DirEntry> sessionFactory) {
        return new SftpRemoteFileTemplate(sessionFactory);
    }
}
