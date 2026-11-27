package be.pxl.services.runtime.poller;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.stereotype.Component;

import be.pxl.services.runtime.config.RuntimePollerProperties;
import be.pxl.services.runtime.config.RuntimeSftpConfig;
import be.pxl.services.runtime.domain.ClaimedInterface;
import be.pxl.services.runtime.domain.IncomingInterface;
import be.pxl.services.runtime.metrics.RuntimeMetrics;
import be.pxl.services.runtime.processor.InterfaceProcessor;
import be.pxl.services.runtime.storage.RuntimeInterfaceStorage;

/**
 * Adaptive SFTP drain-loop poller with bounded parallel worker execution and backpressure.
 *
 * <p>Uses {@code baseIntervalMs + random(0..maxJitterMs)} only while {@code incoming/} is empty.
 * Whenever backlog is present, files are claimed atomically up to {@code workerConcurrency}
 * and drained immediately without idle sleeps.
 */
@Component
@ConditionalOnProperty(prefix = "runtime.poller", name = "enabled", havingValue = "true", matchIfMissing = true)
public class InterfacePoller {

    private static final Logger LOGGER = LoggerFactory.getLogger(InterfacePoller.class);
    static final long BUSY_RETRY_DELAY_MS = 100L;

    enum DrainOutcome {
        IDLE,
        DRAINED,
        WORKERS_BUSY
    }

    private final RuntimeInterfaceStorage storage;
    private final InterfaceProcessor processor;
    private final RuntimePollerProperties properties;
    private final RuntimeMetrics metrics;
    private final TaskScheduler taskScheduler;
    private final ExecutorService workerExecutor;
    private final Semaphore workerSlots;
    private final AtomicBoolean running = new AtomicBoolean(false);

    private final AtomicReference<ScheduledFuture<?>> pollFuture = new AtomicReference<>();
    private final AtomicReference<ScheduledFuture<?>> recoveryFuture = new AtomicReference<>();

    public InterfacePoller(
            RuntimeInterfaceStorage storage,
            InterfaceProcessor processor,
            RuntimePollerProperties properties,
            RuntimeMetrics metrics,
            @Qualifier(RuntimeSftpConfig.RUNTIME_POLLER_SCHEDULER) TaskScheduler taskScheduler,
            @Qualifier(RuntimeSftpConfig.RUNTIME_WORKER_EXECUTOR) ExecutorService workerExecutor
    ) {
        this.storage = storage;
        this.processor = processor;
        this.properties = properties;
        this.metrics = metrics;
        this.taskScheduler = taskScheduler;
        this.workerExecutor = workerExecutor;
        this.workerSlots = new Semaphore(properties.workerConcurrency());
    }

    @EventListener(ApplicationReadyEvent.class)
    public void start() {
        if (!running.compareAndSet(false, true)) {
            return;
        }
        long initialDelayMs = nextRandomDelay(properties.baseIntervalMs());
        LOGGER.info("Starting SFTP InterfacePoller instanceId={} concurrency={} baseIntervalMs={} maxJitterMs={}",
                properties.instanceId(), properties.workerConcurrency(),
                properties.baseIntervalMs(), properties.maxJitterMs());
        scheduleNextPoll(initialDelayMs);
        scheduleNextRecovery(properties.staleRecoveryIntervalMs() + nextJitterMs());
    }

    @PreDestroy
    public void stop() {
        running.set(false);
        cancelFuture(pollFuture.getAndSet(null));
        cancelFuture(recoveryFuture.getAndSet(null));
        awaitActiveWorkers();
    }

    DrainOutcome drainOnce() {
        List<IncomingInterface> candidates = storage.listReadyIncoming(Duration.ofMillis(properties.minFileAgeMs()));
        metrics.setBacklogCount(candidates.size());
        if (candidates.isEmpty()) {
            return DrainOutcome.IDLE;
        }

        int claimedCount = 0;
        for (IncomingInterface candidate : candidates) {
            if (!workerSlots.tryAcquire()) {
                return DrainOutcome.WORKERS_BUSY;
            }
            if (claimAndDispatch(candidate)) {
                claimedCount++;
            }
        }
        return claimedCount > 0 ? DrainOutcome.DRAINED : DrainOutcome.IDLE;
    }

    int recoverStaleOnce() {
        int recovered = storage.recoverStaleClaims(Duration.ofMillis(properties.staleClaimTimeoutMs()));
        if (recovered > 0) {
            LOGGER.info("Recovered {} stale interface claim(s) back to incoming/", recovered);
        }
        return recovered;
    }

    long computeIdleDelayMs() {
        return properties.baseIntervalMs() + nextJitterMs();
    }

    long nextDelayMs(DrainOutcome outcome) {
        return switch (outcome) {
            case DRAINED -> 0L;
            case WORKERS_BUSY -> BUSY_RETRY_DELAY_MS;
            case IDLE -> computeIdleDelayMs();
        };
    }

    void pollAndReschedule() {
        if (!running.get()) {
            return;
        }
        long nextDelay;
        try {
            nextDelay = nextDelayMs(drainOnce());
        } catch (Exception ex) {
            LOGGER.warn("SFTP poll cycle failed; retrying after backoff: {}", ex.getMessage());
            nextDelay = computeIdleDelayMs();
        }
        scheduleNextPoll(nextDelay);
    }

    void recoverStaleAndReschedule() {
        if (!running.get()) {
            return;
        }
        try {
            recoverStaleOnce();
        } catch (Exception ex) {
            LOGGER.warn("Stale-claim recovery failed; retrying later: {}", ex.getMessage());
        }
        scheduleNextRecovery(properties.staleRecoveryIntervalMs() + nextJitterMs());
    }

    private boolean claimAndDispatch(IncomingInterface candidate) {
        Optional<ClaimedInterface> claimed;
        try {
            claimed = storage.tryClaim(candidate, properties.instanceId());
        } catch (Exception ex) {
            workerSlots.release();
            LOGGER.warn("Failed to claim {}: {}", candidate.remotePath(), ex.getMessage());
            return false;
        }
        if (claimed.isEmpty()) {
            workerSlots.release();
            return false;
        }
        submitToWorker(claimed.get());
        return true;
    }

    private void submitToWorker(ClaimedInterface claimed) {
        try {
            workerExecutor.execute(() -> processClaimed(claimed));
        } catch (RuntimeException ex) {
            workerSlots.release();
            LOGGER.error("Failed to dispatch claimed interface {}: {}", claimed.claimedPath(), ex.getMessage());
        }
    }

    private void processClaimed(ClaimedInterface claimed) {
        metrics.workerStarted();
        try {
            byte[] xmlContent = storage.readBytes(claimed);
            processor.process(claimed, xmlContent);
            storage.moveToProcessed(claimed);
            metrics.recordProcessed();
        } catch (Exception ex) {
            LOGGER.error("Failed to process interface {} for customer {}: {}",
                    claimed.filename(), claimed.customer(), ex.getMessage(), ex);
            moveToErrorSafely(claimed, ex);
            metrics.recordFailed();
        } finally {
            metrics.workerFinished();
            workerSlots.release();
        }
    }

    private void moveToErrorSafely(ClaimedInterface claimed, Exception cause) {
        try {
            storage.moveToError(claimed, cause.getMessage());
        } catch (Exception storageEx) {
            LOGGER.error("Also failed to move {} to error/: {}",
                    claimed.claimedPath(), storageEx.getMessage(), storageEx);
        }
    }

    private void scheduleNextPoll(long delayMs) {
        if (running.get()) {
            pollFuture.set(taskScheduler.schedule(this::pollAndReschedule, Instant.now().plusMillis(delayMs)));
        }
    }

    private void scheduleNextRecovery(long delayMs) {
        if (running.get()) {
            recoveryFuture.set(
                    taskScheduler.schedule(this::recoverStaleAndReschedule, Instant.now().plusMillis(delayMs)));
        }
    }

    private void awaitActiveWorkers() {
        int permits = properties.workerConcurrency();
        try {
            boolean drained = workerSlots.tryAcquire(permits, properties.shutdownAwaitSeconds(), TimeUnit.SECONDS);
            if (drained) {
                workerSlots.release(permits);
            } else {
                LOGGER.warn("Timed out waiting for active workers to complete during shutdown");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    }

    private long nextJitterMs() {
        return nextRandomDelay(properties.maxJitterMs());
    }

    private static long nextRandomDelay(long maxInclusiveMs) {
        return maxInclusiveMs > 0 ? ThreadLocalRandom.current().nextLong(maxInclusiveMs + 1) : 0L;
    }

    private static void cancelFuture(ScheduledFuture<?> future) {
        if (future != null) {
            future.cancel(false);
        }
    }
}
