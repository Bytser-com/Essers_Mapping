package be.pxl.services.runtime.poller;

import java.time.Clock;
import java.time.Duration;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.locks.ReentrantLock;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.SmartLifecycle;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.stereotype.Component;

import be.pxl.services.runtime.config.RuntimePollerProperties;
import be.pxl.services.runtime.config.RuntimeSftpConfig;
import be.pxl.services.runtime.domain.ClaimedInterface;
import be.pxl.services.runtime.domain.IncomingInterface;
import be.pxl.services.runtime.exception.RuntimeStorageException;
import be.pxl.services.runtime.metrics.RuntimeMetrics;
import be.pxl.services.runtime.processor.InterfaceProcessor;
import be.pxl.services.runtime.storage.RuntimeInterfaceStorage;

/**
 * Adaptive SFTP drain-loop poller with bounded parallel worker execution and backpressure.
 *
 * <p>Implements {@link SmartLifecycle} at {@link Integer#MAX_VALUE} so polling starts last
 * and stops first — before the SFTP session pool and worker executor are torn down.
 */
@Component
@ConditionalOnProperty(prefix = "runtime.poller", name = "enabled", havingValue = "true", matchIfMissing = true)
public class InterfacePoller implements SmartLifecycle {

    private static final Logger LOGGER = LoggerFactory.getLogger(InterfacePoller.class);
    static final long BUSY_RETRY_DELAY_MS = 500L;

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
    private final Clock clock;
    private final Semaphore workerSlots;

    private final Object lifecycleLock = new Object();
    private final ReentrantLock drainLock = new ReentrantLock();
    private final AtomicBoolean running = new AtomicBoolean(false);
    private final AtomicBoolean stopping = new AtomicBoolean(false);
    private final AtomicBoolean waitingForWorkerSlot = new AtomicBoolean(false);
    private final AtomicReference<ScheduledFuture<?>> pollFuture = new AtomicReference<>();
    private final AtomicReference<ScheduledFuture<?>> recoveryFuture = new AtomicReference<>();

    @Autowired
    public InterfacePoller(
            RuntimeInterfaceStorage storage,
            InterfaceProcessor processor,
            RuntimePollerProperties properties,
            RuntimeMetrics metrics,
            @Qualifier(RuntimeSftpConfig.RUNTIME_POLLER_SCHEDULER) TaskScheduler taskScheduler,
            @Qualifier(RuntimeSftpConfig.RUNTIME_WORKER_EXECUTOR) ExecutorService workerExecutor,
            Clock clock
    ) {
        this.storage = storage;
        this.processor = processor;
        this.properties = properties;
        this.metrics = metrics;
        this.taskScheduler = taskScheduler;
        this.workerExecutor = workerExecutor;
        this.clock = clock;
        this.workerSlots = new Semaphore(properties.workerConcurrency());
    }

    @Override
    public void start() {
        synchronized (lifecycleLock) {
            if (!running.compareAndSet(false, true)) {
                return;
            }
            stopping.set(false);
            waitingForWorkerSlot.set(false);
            long initialDelayMs = nextRandomDelay(properties.baseIntervalMs());
            LOGGER.info("Starting SFTP InterfacePoller instanceId={} concurrency={} baseIntervalMs={} maxJitterMs={}",
                    properties.instanceId(), properties.workerConcurrency(),
                    properties.baseIntervalMs(), properties.maxJitterMs());
            scheduleNextPollLocked(initialDelayMs);
            scheduleNextRecoveryLocked(properties.staleRecoveryIntervalMs() + nextJitterMs());
        }
    }

    @Override
    public void stop() {
        synchronized (lifecycleLock) {
            stopping.set(true);
            running.set(false);
            waitingForWorkerSlot.set(false);
            cancelFuture(pollFuture.getAndSet(null));
            cancelFuture(recoveryFuture.getAndSet(null));
        }
        awaitInFlightDrain();
        awaitActiveWorkers();
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        return Integer.MAX_VALUE;
    }

    DrainOutcome drainOnce() {
        drainLock.lock();
        try {
            return drainUnderLock();
        } finally {
            drainLock.unlock();
        }
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
            metrics.recordPollError();
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
            metrics.recordPollError();
            LOGGER.warn("Stale-claim recovery failed; retrying later: {}", ex.getMessage());
        }
        scheduleNextRecovery(properties.staleRecoveryIntervalMs() + nextJitterMs());
    }

    private DrainOutcome drainUnderLock() {
        if (stopping.get()) {
            return DrainOutcome.IDLE;
        }
        if (workerSlots.availablePermits() == 0) {
            waitingForWorkerSlot.set(true);
            return DrainOutcome.WORKERS_BUSY;
        }

        List<IncomingInterface> candidates = storage.listReadyIncoming(Duration.ofMillis(properties.minFileAgeMs()));
        metrics.setBacklogCount(candidates.size());
        if (candidates.isEmpty()) {
            return DrainOutcome.IDLE;
        }

        int claimedCount = 0;
        for (IncomingInterface candidate : candidates) {
            if (stopping.get()) {
                break;
            }
            if (!workerSlots.tryAcquire()) {
                waitingForWorkerSlot.set(true);
                metrics.setBacklogCount(Math.max(0, candidates.size() - claimedCount));
                return DrainOutcome.WORKERS_BUSY;
            }
            if (claimAndDispatch(candidate)) {
                claimedCount++;
            }
        }

        metrics.setBacklogCount(Math.max(0, candidates.size() - claimedCount));
        if (claimedCount == 0 || stopping.get()) {
            return DrainOutcome.IDLE;
        }
        if (workerSlots.availablePermits() == 0) {
            waitingForWorkerSlot.set(true);
            return DrainOutcome.WORKERS_BUSY;
        }
        return candidates.size() >= properties.workerConcurrency() ? DrainOutcome.DRAINED : DrainOutcome.IDLE;
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
        return submitToWorker(claimed.get());
    }

    private boolean submitToWorker(ClaimedInterface claimed) {
        try {
            workerExecutor.execute(() -> processClaimed(claimed));
            return true;
        } catch (RuntimeException ex) {
            workerSlots.release();
            LOGGER.error("Failed to dispatch claimed interface {}: {}", claimed.claimedPath(), ex.getMessage());
            return false;
        }
    }

    private void processClaimed(ClaimedInterface claimed) {
        long startNanos = System.nanoTime();
        metrics.workerStarted();
        try {
            byte[] xmlContent = readClaimedBytes(claimed);
            if (xmlContent == null) {
                return;
            }
            processor.process(claimed, xmlContent);
            if (finalizeProcessed(claimed)) {
                metrics.recordProcessed();
            }
        } catch (Exception ex) {
            LOGGER.error("Failed to process interface {} for customer {}: {}",
                    claimed.filename(), claimed.customer(), ex.getMessage(), ex);
            moveToErrorSafely(claimed, formatFailureReason(ex));
            metrics.recordFailed();
        } finally {
            metrics.recordProcessingDuration(System.nanoTime() - startNanos);
            metrics.workerFinished();
            workerSlots.release();
            wakePollerIfWaiting();
        }
    }

    private byte[] readClaimedBytes(ClaimedInterface claimed) {
        try {
            return storage.readBytes(claimed);
        } catch (RuntimeStorageException storageEx) {
            // Transient SFTP failure: keep file in processing/ for stale-claim recovery instead of error/.
            LOGGER.warn("Transient SFTP error reading {}; leaving in processing/ for recovery: {}",
                    claimed.claimedPath(), storageEx.getMessage());
            return null;
        }
    }

    private boolean finalizeProcessed(ClaimedInterface claimed) {
        try {
            storage.moveToProcessed(claimed);
            return true;
        } catch (RuntimeStorageException storageEx) {
            // Processing already succeeded; do not move to error/ with a misleading failure note.
            LOGGER.error("Processed {} successfully but failed to move to processed/: {}",
                    claimed.claimedPath(), storageEx.getMessage(), storageEx);
            return false;
        }
    }

    private void moveToErrorSafely(ClaimedInterface claimed, String reason) {
        try {
            storage.moveToError(claimed, reason);
        } catch (Exception storageEx) {
            LOGGER.error("Also failed to move {} to error/: {}",
                    claimed.claimedPath(), storageEx.getMessage(), storageEx);
        }
    }

    private void wakePollerIfWaiting() {
        if (running.get() && waitingForWorkerSlot.compareAndSet(true, false)) {
            scheduleNextPoll(0L);
        }
    }

    private void scheduleNextPoll(long delayMs) {
        synchronized (lifecycleLock) {
            scheduleNextPollLocked(delayMs);
        }
    }

    private void scheduleNextPollLocked(long delayMs) {
        if (!running.get()) {
            return;
        }
        ScheduledFuture<?> next = taskScheduler.schedule(this::pollAndReschedule, clock.instant().plusMillis(delayMs));
        ScheduledFuture<?> previous = pollFuture.getAndSet(next);
        if (previous != null && previous != next) {
            previous.cancel(false);
        }
    }

    private void scheduleNextRecovery(long delayMs) {
        synchronized (lifecycleLock) {
            scheduleNextRecoveryLocked(delayMs);
        }
    }

    private void scheduleNextRecoveryLocked(long delayMs) {
        if (!running.get()) {
            return;
        }
        ScheduledFuture<?> next = taskScheduler.schedule(
                this::recoverStaleAndReschedule, clock.instant().plusMillis(delayMs));
        ScheduledFuture<?> previous = recoveryFuture.getAndSet(next);
        if (previous != null && previous != next) {
            previous.cancel(false);
        }
    }

    private void awaitInFlightDrain() {
        try {
            if (drainLock.tryLock(properties.shutdownAwaitSeconds(), TimeUnit.SECONDS)) {
                drainLock.unlock();
            } else {
                LOGGER.warn("Timed out waiting for in-flight SFTP drain cycle during shutdown");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
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
        if (maxInclusiveMs <= 0) {
            return 0L;
        }
        long bound = maxInclusiveMs == Long.MAX_VALUE ? Long.MAX_VALUE : maxInclusiveMs + 1;
        return ThreadLocalRandom.current().nextLong(bound);
    }

    static String formatFailureReason(Exception cause) {
        String type = cause.getClass().getSimpleName();
        String message = cause.getMessage();
        return (message == null || message.isBlank()) ? type : type + ": " + message.trim();
    }

    private static void cancelFuture(ScheduledFuture<?> future) {
        if (future != null) {
            future.cancel(false);
        }
    }
}
