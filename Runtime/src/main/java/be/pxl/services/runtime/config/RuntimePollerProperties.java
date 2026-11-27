package be.pxl.services.runtime.config;

import java.util.UUID;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Configuration properties for the adaptive SFTP drain-loop poller and bounded parallel worker pool.
 */
@ConfigurationProperties(prefix = "runtime.poller")
public record RuntimePollerProperties(
        boolean enabled,
        long baseIntervalMs,
        long maxJitterMs,
        long minFileAgeMs,
        int workerConcurrency,
        long staleClaimTimeoutMs,
        long staleRecoveryIntervalMs,
        int shutdownAwaitSeconds,
        String instanceId
) {
    public static final long DEFAULT_BASE_INTERVAL_MS = 5_000L;
    public static final long DEFAULT_MAX_JITTER_MS = 1_500L;
    public static final long DEFAULT_MIN_FILE_AGE_MS = 3_000L;
    public static final int DEFAULT_WORKER_CONCURRENCY = 4;
    public static final long DEFAULT_STALE_CLAIM_TIMEOUT_MS = 300_000L;
    public static final long DEFAULT_STALE_RECOVERY_INTERVAL_MS = 60_000L;
    public static final int DEFAULT_SHUTDOWN_AWAIT_SECONDS = 30;
    private static final int MIN_SESSION_POOL_SIZE = 4;
    private static final int EXTRA_POLLER_SESSIONS = 2;

    public RuntimePollerProperties {
        if (baseIntervalMs <= 0) {
            baseIntervalMs = DEFAULT_BASE_INTERVAL_MS;
        }
        if (maxJitterMs < 0) {
            maxJitterMs = 0L;
        }
        if (minFileAgeMs < 0) {
            minFileAgeMs = 0L;
        }
        if (workerConcurrency <= 0) {
            workerConcurrency = DEFAULT_WORKER_CONCURRENCY;
        }
        if (staleClaimTimeoutMs <= 0) {
            staleClaimTimeoutMs = DEFAULT_STALE_CLAIM_TIMEOUT_MS;
        }
        if (staleRecoveryIntervalMs <= 0) {
            staleRecoveryIntervalMs = DEFAULT_STALE_RECOVERY_INTERVAL_MS;
        }
        if (shutdownAwaitSeconds <= 0) {
            shutdownAwaitSeconds = DEFAULT_SHUTDOWN_AWAIT_SECONDS;
        }
        instanceId = sanitizeInstanceId(instanceId);
    }

    /**
     * Size the SFTP session cache so parallel workers and the poller never contend on a single session.
     */
    public int recommendedSessionPoolSize() {
        return Math.max(MIN_SESSION_POOL_SIZE, workerConcurrency + EXTRA_POLLER_SESSIONS);
    }

    private static String sanitizeInstanceId(String raw) {
        String cleaned = raw == null ? "" : raw.trim().replaceAll("[^A-Za-z0-9._-]", "");
        if (!cleaned.isEmpty()) {
            return cleaned;
        }
        return "runtime-" + UUID.randomUUID().toString().substring(0, 8);
    }
}
