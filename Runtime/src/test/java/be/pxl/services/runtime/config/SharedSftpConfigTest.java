package be.pxl.services.runtime.config;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.integration.file.remote.session.CachingSessionFactory;
import org.springframework.integration.sftp.session.DefaultSftpSessionFactory;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

class SharedSftpConfigTest {

    // Only the shared SFTP configuration, no connection is made
    private final ApplicationContextRunner contextRunner = new ApplicationContextRunner()
            .withUserConfiguration(SharedSftpConfig.class)
            .withPropertyValues(
                    "sftp.shared.host=sftp-shared",
                    "sftp.shared.port=70000",
                    "sftp.shared.password=secret",
                    "sftp.shared.packages-path=/Packages/");

    @Test
    @DisplayName("TC-52-03 the shared SFTP beans are created with their own names")
    void createsNamedBeans() {
        contextRunner.run(context -> {
            assertInstanceOf(DefaultSftpSessionFactory.class, context.getBean(SharedSftpConfig.SHARED_SFTP_CONNECTION));
            assertInstanceOf(CachingSessionFactory.class, context.getBean(SharedSftpConfig.SHARED_SFTP_SESSION_FACTORY));
            assertInstanceOf(SftpRemoteFileTemplate.class, context.getBean(SharedSftpConfig.SHARED_SFTP_TEMPLATE));
        });
    }

    @Test
    @DisplayName("TC-52-03 the bound settings use a valid port and hide the password")
    void bindsSettingsSafely() {
        contextRunner.run(context -> {
            SharedSftpProperties properties = context.getBean(SharedSftpProperties.class);

            assertEquals("sftp-shared", properties.host());
            assertEquals(SharedSftpProperties.DEFAULT_PORT, properties.port());
            assertEquals(SharedSftpProperties.DEFAULT_TIMEOUT_MS, properties.timeoutMs());
            assertFalse(properties.toString().contains("secret"));
        });
    }
}
