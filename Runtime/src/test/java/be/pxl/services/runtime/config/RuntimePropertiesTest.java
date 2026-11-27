package be.pxl.services.runtime.config;

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
    @DisplayName("RuntimeSftpProperties applies safe defaults when values are blank or invalid")
    void sftpPropertiesApplyDefaults() {
        RuntimeSftpProperties props = new RuntimeSftpProperties(
                " ", 0, "", null, null, null, "", true, -5
        );

        assertEquals(RuntimeSftpProperties.DEFAULT_HOST, props.host());
        assertEquals(RuntimeSftpProperties.DEFAULT_PORT, props.port());
        assertEquals(RuntimeSftpProperties.DEFAULT_USER, props.user());
        assertEquals("", props.password());
        assertEquals(RuntimeSftpProperties.DEFAULT_REMOTE_DIR, props.remoteDir());
        assertTrue(props.allowUnknownKeys());
        assertEquals(RuntimeSftpProperties.DEFAULT_SESSION_WAIT_TIMEOUT_MS, props.sessionWaitTimeoutMs());
    }

    @Test
    @DisplayName("RuntimePollerProperties applies defaults and computes session pool size from concurrency")
    void pollerPropertiesApplyDefaultsAndPoolSize() {
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
        assertEquals(6, props.recommendedSessionPoolSize());
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
        assertEquals(10, props.recommendedSessionPoolSize());
        assertEquals("runtime-pod-1badchars", props.instanceId());
    }

    @Test
    @DisplayName("RuntimeSftpConfig wires CachingSessionFactory, SftpRemoteFileTemplate, scheduler and worker executor")
    void configCreatesInfrastructureBeans() {
        RuntimeSftpConfig config = new RuntimeSftpConfig();
        RuntimeSftpProperties sftpProps = new RuntimeSftpProperties(
                "sftp-runtime", 22, "runtimeuser", "", null, null, "/Clients", true, 5_000L
        );
        RuntimePollerProperties pollerProps = new RuntimePollerProperties(
                true, 5_000L, 1_500L, 3_000L, 6, 300_000L, 60_000L, 20, "pod-a"
        );

        SessionFactory<SftpClient.DirEntry> factory =
                config.runtimeSftpSessionFactory(sftpProps, pollerProps, new DefaultResourceLoader());
        SftpRemoteFileTemplate template = config.runtimeSftpTemplate(factory);
        ThreadPoolTaskScheduler scheduler = config.runtimePollerTaskScheduler(pollerProps);
        ExecutorService executor = config.runtimeWorkerExecutor();

        try {
            assertInstanceOf(CachingSessionFactory.class, factory);
            assertNotNull(template);
            assertNotNull(scheduler);
            assertNotNull(executor);
        } finally {
            executor.shutdownNow();
        }
    }
}
