package be.pxl.services.runtime.config;

import java.time.Clock;
import java.util.concurrent.ExecutorService;

import org.apache.sshd.sftp.client.SftpClient;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.DefaultResourceLoader;
import org.springframework.integration.file.remote.session.CachingSessionFactory;
import org.springframework.integration.file.remote.session.SessionFactory;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RuntimePropertiesTest {

    @Test
    @DisplayName("RuntimeSftpProperties applies safe defaults when values are blank or out of range")
    void sftpPropertiesApplyDefaults() {
        RuntimeSftpProperties props = new RuntimeSftpProperties(
                " ", 70_000, "", null, null, null, null, "", false, -5, 0, -1
        );

        assertEquals(RuntimeSftpProperties.DEFAULT_HOST, props.host());
        assertEquals(RuntimeSftpProperties.DEFAULT_PORT, props.port());
        assertEquals(RuntimeSftpProperties.DEFAULT_USER, props.user());
        assertEquals("", props.password());
        assertEquals(RuntimeSftpProperties.DEFAULT_REMOTE_DIR, props.remoteDir());
        assertFalse(props.allowUnknownKeys());
        assertEquals(RuntimeSftpProperties.DEFAULT_SESSION_WAIT_TIMEOUT_MS, props.sessionWaitTimeoutMs());
        assertEquals(RuntimeSftpProperties.DEFAULT_CONNECT_TIMEOUT_MS, props.connectTimeoutMs());
        assertEquals(RuntimeSftpProperties.DEFAULT_MAX_FILE_SIZE_BYTES, props.maxFileSizeBytes());
    }

    @Test
    @DisplayName("RuntimeSftpProperties redacts credentials in toString output")
    void sftpPropertiesRedactSecretsInToString() {
        RuntimeSftpProperties props = new RuntimeSftpProperties(
                "sftp-runtime", 22, "runtimeuser", "super-secret-value",
                "classpath:key.pem", "key-passphrase-value", "classpath:known_hosts",
                "/Clients", false, 5_000L, 4_000, 10_000L
        );

        String rendered = props.toString();

        assertFalse(rendered.contains("super-secret-value"));
        assertFalse(rendered.contains("key-passphrase-value"));
        assertTrue(rendered.contains("password=****"));
        assertTrue(rendered.contains("privateKeyPassphrase=****"));
        assertTrue(rendered.contains("host=sftp-runtime"));
    }

    @Test
    @DisplayName("RuntimePollerProperties applies defaults and generates fallback instanceId")
    void pollerPropertiesApplyDefaults() {
        RuntimePollerProperties props = new RuntimePollerProperties(
                true, 0, -10, -5, 0, 0, 0, 0, "  "
        );

        assertTrue(props.enabled());
        assertEquals(RuntimePollerProperties.DEFAULT_BASE_INTERVAL_MS, props.baseIntervalMs());
        assertEquals(0L, props.maxJitterMs());
        assertEquals(0L, props.minFileAgeMs());
        assertEquals(RuntimePollerProperties.DEFAULT_WORKER_CONCURRENCY, props.workerConcurrency());
        assertEquals(RuntimePollerProperties.DEFAULT_STALE_CLAIM_TIMEOUT_MS, props.staleClaimTimeoutMs());
        assertEquals(RuntimePollerProperties.DEFAULT_STALE_RECOVERY_INTERVAL_MS, props.staleRecoveryIntervalMs());
        assertEquals(RuntimePollerProperties.DEFAULT_SHUTDOWN_AWAIT_SECONDS, props.shutdownAwaitSeconds());
        assertTrue(props.instanceId().startsWith("runtime-"));
    }

    @Test
    @DisplayName("RuntimePollerProperties sanitizes custom instanceId and keeps valid values")
    void pollerPropertiesSanitizeInstanceId() {
        RuntimePollerProperties props = new RuntimePollerProperties(
                false, 2_000L, 500L, 1_000L, 8, 120_000L, 30_000L, 15, "runtime-pod-1/bad!chars"
        );

        assertFalse(props.enabled());
        assertEquals(2_000L, props.baseIntervalMs());
        assertEquals(500L, props.maxJitterMs());
        assertEquals(1_000L, props.minFileAgeMs());
        assertEquals(8, props.workerConcurrency());
        assertEquals(10, RuntimeSftpConfig.recommendedSessionPoolSize(props.workerConcurrency()));
        assertEquals(4, RuntimeSftpConfig.recommendedSessionPoolSize(1));
        assertEquals("runtime-pod-1badchars", props.instanceId());
    }

    @Test
    @DisplayName("RuntimeSftpConfig wires CachingSessionFactory with testSession, privateKey, knownHosts and beans")
    void configCreatesInfrastructureBeans() {
        RuntimeSftpConfig config = new RuntimeSftpConfig();
        RuntimeSftpProperties sftpProps = new RuntimeSftpProperties(
                "sftp-runtime", 22, "runtimeuser", "dummy-pw",
                "classpath:application.properties", "dummy-pass", "classpath:application.properties",
                "/Clients", false, 5_000L, 8_000, 1_048_576L
        );
        RuntimePollerProperties pollerProps = new RuntimePollerProperties(
                true, 5_000L, 1_500L, 3_000L, 6, 300_000L, 60_000L, 20, "pod-a"
        );

        SessionFactory<SftpClient.DirEntry> factory =
                config.runtimeSftpSessionFactory(sftpProps, pollerProps, new DefaultResourceLoader());
        SftpRemoteFileTemplate template = config.runtimeSftpTemplate(factory);
        ThreadPoolTaskScheduler scheduler = config.runtimePollerTaskScheduler(pollerProps);
        ExecutorService executor = config.runtimeWorkerExecutor();
        Clock clock = config.runtimeClock();

        try {
            assertInstanceOf(CachingSessionFactory.class, factory);
            assertNotNull(template);
            assertNotNull(scheduler);
            assertNotNull(executor);
            assertNotNull(clock);
        } finally {
            executor.shutdownNow();
        }
    }
}
