package be.pxl.services.runtime.config;

import java.util.UUID;
import java.util.regex.Pattern;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
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
    private static final Logger LOGGER = LoggerFactory.getLogger(RuntimePollerProperties.class);
    private static final Pattern INVALID_INSTANCE_ID_CHARS = Pattern.compile("[^A-Za-z0-9_-]");

    public static final long DEFAULT_BASE_INTERVAL_MS = 5_000L;
    public static final long DEFAULT_MAX_JITTER_MS = 1_500L;
    public static final long DEFAULT_MIN_FILE_AGE_MS = 3_000L;
    public static final int DEFAULT_WORKER_CONCURRENCY = 4;
    public static final long DEFAULT_STALE_CLAIM_TIMEOUT_MS = 300_000L;
    public static final long DEFAULT_STALE_RECOVERY_INTERVAL_MS = 60_000L;
    public static final int DEFAULT_SHUTDOWN_AWAIT_SECONDS = 20;

    public RuntimePollerProperties {
        baseIntervalMs = positiveOrDefault("base-interval-ms", baseIntervalMs, DEFAULT_BASE_INTERVAL_MS);
        maxJitterMs = nonNegativeOrZero("max-jitter-ms", maxJitterMs);
        minFileAgeMs = nonNegativeOrZero("min-file-age-ms", minFileAgeMs);
        if (workerConcurrency <= 0) {
            LOGGER.warn("Invalid runtime.poller.worker-concurrency={}; falling back to {}",
                    workerConcurrency, DEFAULT_WORKER_CONCURRENCY);
            workerConcurrency = DEFAULT_WORKER_CONCURRENCY;
        }
        staleClaimTimeoutMs = positiveOrDefault(
                "stale-claim-timeout-ms", staleClaimTimeoutMs, DEFAULT_STALE_CLAIM_TIMEOUT_MS);
        staleRecoveryIntervalMs = positiveOrDefault(
                "stale-recovery-interval-ms", staleRecoveryIntervalMs, DEFAULT_STALE_RECOVERY_INTERVAL_MS);
        if (shutdownAwaitSeconds <= 0) {
            LOGGER.warn("Invalid runtime.poller.shutdown-await-seconds={}; falling back to {}",
                    shutdownAwaitSeconds, DEFAULT_SHUTDOWN_AWAIT_SECONDS);
            shutdownAwaitSeconds = DEFAULT_SHUTDOWN_AWAIT_SECONDS;
        }
        instanceId = resolveInstanceId(instanceId);
    }

    /**
     * Strip unsafe path characters from a pod/instance identifier so it can safely appear
     * inside SFTP {@code .processing} filenames.
     */
    public static String cleanInstanceId(String raw) {
        if (raw == null) {
            return "";
        }
        String normalized = raw.trim().replace('.', '-');
        return INVALID_INSTANCE_ID_CHARS.matcher(normalized).replaceAll("");
    }

    private static String resolveInstanceId(String raw) {
        String cleaned = cleanInstanceId(raw);
        if (!cleaned.isEmpty()) {
            return cleaned;
        }
        return "runtime-" + UUID.randomUUID().toString().substring(0, 8);
    }

    private static long positiveOrDefault(String name, long value, long defaultValue) {
        if (value <= 0) {
            LOGGER.warn("Invalid runtime.poller.{}={}; falling back to {}", name, value, defaultValue);
            return defaultValue;
        }
        return value;
    }

    private static long nonNegativeOrZero(String name, long value) {
        if (value < 0) {
            LOGGER.warn("Invalid runtime.poller.{}={}; clamping to 0", name, value);
            return 0L;
        }
        return value;
    }
}
