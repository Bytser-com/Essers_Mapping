package be.pxl.services.runtime.poller;

import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.scheduling.TaskScheduler;

import be.pxl.services.runtime.config.RuntimePollerProperties;
import be.pxl.services.runtime.domain.ClaimedInterface;
import be.pxl.services.runtime.domain.IncomingInterface;
import be.pxl.services.runtime.exception.InterfacePayloadTooLargeException;
import be.pxl.services.runtime.exception.RuntimeStorageException;
import be.pxl.services.runtime.metrics.RuntimeMetrics;
import be.pxl.services.runtime.poller.InterfacePoller.DrainOutcome;
import be.pxl.services.runtime.processor.InterfaceProcessor;
import be.pxl.services.runtime.storage.RuntimeInterfaceStorage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class InterfacePollerTest {

    private static final String CUSTOMER = "nouryon";
    private static final String MESSAGE_TYPE = "outbound";
    private static final String BASE_DIR = "/Clients/nouryon/outbound";
    private static final String INSTANCE_ID = "pod-test-1";
    private static final byte[] SAMPLE_XML = "<order/>".getBytes(StandardCharsets.UTF_8);

    private RuntimeInterfaceStorage storage;
    private InterfaceProcessor processor;
    private TaskScheduler taskScheduler;
    private ExecutorService workerExecutor;
    private SimpleMeterRegistry meterRegistry;
    private RuntimeMetrics metrics;
    private MutableClock clock;
    private InterfacePoller poller;

    @BeforeEach
    void setUp() {
        storage = mock(RuntimeInterfaceStorage.class);
        processor = mock(InterfaceProcessor.class);
        taskScheduler = mock(TaskScheduler.class);
        workerExecutor = Executors.newSingleThreadExecutor();
        meterRegistry = new SimpleMeterRegistry();
        metrics = new RuntimeMetrics(meterRegistry);
        clock = new MutableClock(Instant.parse("2026-11-27T12:00:00Z"));
        poller = new InterfacePoller(
                storage, processor, defaultProperties(1_500L, 4), metrics, taskScheduler, workerExecutor, clock);
    }

    @AfterEach
    void tearDown() {
        poller.stop();
        workerExecutor.shutdownNow();
    }

    @Test
    @DisplayName("drainOnce claims, processes, moves file to processed/ and updates metrics without extra scan")
    void drainOnceProcessesClaimedFileAndUpdatesMetrics() {
        IncomingInterface incoming = incomingFile("order_1.xml");
        ClaimedInterface claimed = claimedFile("order_1.xml");

        when(storage.listReadyIncoming(Duration.ofMillis(3_000L))).thenReturn(List.of(incoming));
        when(storage.tryClaim(incoming, INSTANCE_ID)).thenReturn(Optional.of(claimed));
        when(storage.readBytes(claimed)).thenReturn(SAMPLE_XML);

        DrainOutcome outcome = poller.drainOnce();
        poller.stop();

        assertEquals(DrainOutcome.IDLE, outcome);
        verify(processor).process(claimed, SAMPLE_XML);
        verify(storage).moveToProcessed(claimed);
        assertEquals(0, metrics.backlogCount());
        assertEquals(0, metrics.activeWorkers());
        assertEquals(1.0, meterRegistry.get(RuntimeMetrics.FILES_PROCESSED_METRIC).counter().count());
        assertEquals(0.0, meterRegistry.get(RuntimeMetrics.FILES_FAILED_METRIC).counter().count());
        assertEquals(1L, meterRegistry.get(RuntimeMetrics.PROCESSING_DURATION_METRIC).timer().count());
    }

    @Test
    @DisplayName("WORKERS_BUSY skips SFTP scans immediately, but refreshes backlog gauge after baseIntervalMs")
    void workersBusySkipsImmediateScanAndRefreshesBacklogAfterBaseInterval() throws Exception {
        InterfacePoller singleWorkerPoller = new InterfacePoller(
                storage, processor, defaultProperties(0L, 1), metrics, taskScheduler, workerExecutor, clock);
        IncomingInterface incoming = incomingFile("slow.xml");
        ClaimedInterface claimed = claimedFile("slow.xml");

        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch releaseWorker = new CountDownLatch(1);
        when(storage.listReadyIncoming(any()))
                .thenReturn(List.of(incoming))
                .thenReturn(List.of(incomingFile("q1.xml"), incomingFile("q2.xml"), incomingFile("q3.xml")));
        when(storage.tryClaim(incoming, INSTANCE_ID)).thenReturn(Optional.of(claimed));
        when(storage.readBytes(claimed)).thenReturn(SAMPLE_XML);
        doAnswer(inv -> {
            workerStarted.countDown();
            releaseWorker.await(5, TimeUnit.SECONDS);
            return null;
        }).when(processor).process(eq(claimed), any());

        try {
            assertEquals(DrainOutcome.WORKERS_BUSY, singleWorkerPoller.drainOnce());
            assertTrue(workerStarted.await(5, TimeUnit.SECONDS));

            // Within baseIntervalMs: zero extra SFTP scan!
            assertEquals(DrainOutcome.WORKERS_BUSY, singleWorkerPoller.drainOnce());
            verify(storage, times(1)).listReadyIncoming(any());

            // After baseIntervalMs (5s): refreshes backlog gauge so KEDA/HPA sees queued burst!
            clock.advance(Duration.ofSeconds(5));
            assertEquals(DrainOutcome.WORKERS_BUSY, singleWorkerPoller.drainOnce());
            verify(storage, times(2)).listReadyIncoming(any());
            assertEquals(3, metrics.backlogCount());
        } finally {
            releaseWorker.countDown();
            singleWorkerPoller.stop();
        }
    }

    @Test
    @DisplayName("drainOnce subtracts files already claimed by other pods from backlog metric")
    void drainOnceSkipsAlreadyClaimedFileAndUpdatesBacklog() {
        IncomingInterface incoming = incomingFile("order_1.xml");
        when(storage.listReadyIncoming(any())).thenReturn(List.of(incoming));
        when(storage.tryClaim(incoming, INSTANCE_ID)).thenReturn(Optional.empty());

        DrainOutcome outcome = poller.drainOnce();

        assertEquals(DrainOutcome.IDLE, outcome);
        assertEquals(0, metrics.backlogCount());
        verify(storage, never()).readBytes(any());
        verify(processor, never()).process(any(), any());
    }

    @Test
    @DisplayName("drainOnce isolates processing errors, includes exception type and quarantines oversized files")
    void drainOnceIsolatesFailuresPerFile() {
        IncomingInterface badIncoming = incomingFile("bad.xml");
        IncomingInterface oversizedIncoming = incomingFile("huge.xml");
        IncomingInterface goodIncoming = incomingFile("good.xml");
        ClaimedInterface badClaimed = claimedFile("bad.xml");
        ClaimedInterface oversizedClaimed = claimedFile("huge.xml");
        ClaimedInterface goodClaimed = claimedFile("good.xml");

        when(storage.listReadyIncoming(any())).thenReturn(List.of(badIncoming, oversizedIncoming, goodIncoming));
        when(storage.tryClaim(badIncoming, INSTANCE_ID)).thenReturn(Optional.of(badClaimed));
        when(storage.tryClaim(oversizedIncoming, INSTANCE_ID)).thenReturn(Optional.of(oversizedClaimed));
        when(storage.tryClaim(goodIncoming, INSTANCE_ID)).thenReturn(Optional.of(goodClaimed));
        when(storage.readBytes(badClaimed)).thenReturn(SAMPLE_XML);
        when(storage.readBytes(oversizedClaimed))
                .thenThrow(new InterfacePayloadTooLargeException("Exceeds 25MB limit"));
        when(storage.readBytes(goodClaimed)).thenReturn(SAMPLE_XML);
        doThrow(new NullPointerException()).when(processor).process(eq(badClaimed), any());

        poller.drainOnce();
        poller.stop();

        verify(storage).moveToError(badClaimed, "NullPointerException");
        verify(storage).moveToError(oversizedClaimed, "InterfacePayloadTooLargeException: Exceeds 25MB limit");
        verify(storage).moveToProcessed(goodClaimed);
        assertEquals(2.0, meterRegistry.get(RuntimeMetrics.FILES_FAILED_METRIC).counter().count());
        assertEquals(1.0, meterRegistry.get(RuntimeMetrics.FILES_PROCESSED_METRIC).counter().count());
    }

    @Test
    @DisplayName("Transient readBytes or moveToProcessed SFTP errors record storage metric without moving to error/")
    void transientStorageErrorsRecordMetricWithoutQuarantine() {
        IncomingInterface readFailIncoming = incomingFile("read_blip.xml");
        IncomingInterface moveFailIncoming = incomingFile("move_blip.xml");
        ClaimedInterface readFailClaimed = claimedFile("read_blip.xml");
        ClaimedInterface moveFailClaimed = claimedFile("move_blip.xml");

        when(storage.listReadyIncoming(any())).thenReturn(List.of(readFailIncoming, moveFailIncoming));
        when(storage.tryClaim(readFailIncoming, INSTANCE_ID)).thenReturn(Optional.of(readFailClaimed));
        when(storage.tryClaim(moveFailIncoming, INSTANCE_ID)).thenReturn(Optional.of(moveFailClaimed));
        when(storage.readBytes(readFailClaimed)).thenThrow(new RuntimeStorageException("SFTP timeout"));
        when(storage.readBytes(moveFailClaimed)).thenReturn(SAMPLE_XML);
        doThrow(new RuntimeStorageException("SFTP reset")).when(storage).moveToProcessed(moveFailClaimed);

        poller.drainOnce();
        poller.stop();

        verify(storage, never()).moveToError(any(), any());
        verify(processor, never()).process(eq(readFailClaimed), any());
        verify(processor).process(moveFailClaimed, SAMPLE_XML);
        assertEquals(2.0, meterRegistry.get(RuntimeMetrics.STORAGE_ERRORS_METRIC).counter().count());
        assertEquals(0.0, meterRegistry.get(RuntimeMetrics.FILES_FAILED_METRIC).counter().count());
        assertEquals(0.0, meterRegistry.get(RuntimeMetrics.FILES_PROCESSED_METRIC).counter().count());
    }

    @Test
    @DisplayName("claim exceptions, executor rejections and moveToError failures release worker slots cleanly")
    void errorPathsReleaseWorkerSlotsAndSurvive() {
        ExecutorService rejectingExecutor = mock(ExecutorService.class);
        doThrow(new RejectedExecutionException("shutting down")).when(rejectingExecutor).execute(any());

        InterfacePoller rejectingPoller = new InterfacePoller(
                storage, processor, defaultProperties(0L, 2), metrics, taskScheduler, rejectingExecutor, clock);
        IncomingInterface f1 = incomingFile("f1.xml");
        IncomingInterface f2 = incomingFile("f2.xml");
        when(storage.listReadyIncoming(any())).thenReturn(List.of(f1, f2));
        when(storage.tryClaim(f1, INSTANCE_ID)).thenThrow(new RuntimeStorageException("claim error"));
        when(storage.tryClaim(f2, INSTANCE_ID)).thenReturn(Optional.of(claimedFile("f2.xml")));

        DrainOutcome outcome = rejectingPoller.drainOnce();
        rejectingPoller.stop();

        assertEquals(DrainOutcome.IDLE, outcome);
        assertEquals(0, metrics.activeWorkers());

        IncomingInterface bad = incomingFile("bad2.xml");
        ClaimedInterface badClaimed = claimedFile("bad2.xml");
        when(storage.listReadyIncoming(any())).thenReturn(List.of(bad));
        when(storage.tryClaim(bad, INSTANCE_ID)).thenReturn(Optional.of(badClaimed));
        when(storage.readBytes(badClaimed)).thenReturn(SAMPLE_XML);
        doThrow(new IllegalStateException("invalid")).when(processor).process(eq(badClaimed), any());
        doThrow(new RuntimeStorageException("disk full")).when(storage).moveToError(eq(badClaimed), any());

        poller.drainOnce();
        poller.stop();
        assertEquals(1.0, meterRegistry.get(RuntimeMetrics.FILES_FAILED_METRIC).counter().count());
    }

    @Test
    @DisplayName("nextDelayMs drains immediately on full batch and applies jitter while idle")
    void nextDelayUsesDrainLoopAndIdleJitter() {
        assertEquals(0L, poller.nextDelayMs(DrainOutcome.DRAINED));
        assertEquals(InterfacePoller.BUSY_RETRY_DELAY_MS, poller.nextDelayMs(DrainOutcome.WORKERS_BUSY));

        for (int i = 0; i < 25; i++) {
            long idleDelay = poller.nextDelayMs(DrainOutcome.IDLE);
            assertTrue(idleDelay >= 5_000L && idleDelay <= 6_500L,
                    "Expected idle delay in [5000, 6500], got " + idleDelay);
        }

        InterfacePoller zeroJitterPoller = new InterfacePoller(
                storage, processor, defaultProperties(0L, 4), metrics, taskScheduler, workerExecutor, clock);
        assertEquals(5_000L, zeroJitterPoller.computeIdleDelayMs());
    }

    @Test
    @DisplayName("SmartLifecycle start/stop schedules, handles outages and records poll errors")
    void lifecycleSchedulesHandlesOutagesAndStopsCleanly() {
        ScheduledFuture<?> future = mock(ScheduledFuture.class);
        when(taskScheduler.schedule(any(Runnable.class), any(Instant.class))).thenAnswer(inv -> future);
        when(storage.listReadyIncoming(any())).thenThrow(new RuntimeStorageException("SFTP offline"));
        when(storage.recoverStaleClaims(any())).thenThrow(new RuntimeStorageException("SFTP offline"));

        assertFalse(poller.isRunning());
        assertEquals(Integer.MAX_VALUE, poller.getPhase());

        poller.start();
        assertTrue(poller.isRunning());
        poller.pollAndReschedule();
        poller.recoverStaleAndReschedule();
        poller.stop();

        assertFalse(poller.isRunning());
        assertEquals(2.0, meterRegistry.get(RuntimeMetrics.POLL_ERRORS_METRIC).counter().count());
        verify(taskScheduler, times(4)).schedule(any(Runnable.class), any(Instant.class));
        verify(future, times(2)).cancel(false);
    }

    @Test
    @DisplayName("recoverStaleOnce delegates timeout to storage")
    void recoverStaleOnceDelegatesToStorage() {
        when(storage.recoverStaleClaims(Duration.ofMillis(300_000L))).thenReturn(2);

        assertEquals(2, poller.recoverStaleOnce());
        verify(storage).recoverStaleClaims(Duration.ofMillis(300_000L));
    }

    private RuntimePollerProperties defaultProperties(long maxJitterMs, int concurrency) {
        return new RuntimePollerProperties(
                true, 5_000L, maxJitterMs, 3_000L, concurrency, 300_000L, 60_000L, 5, INSTANCE_ID
        );
    }

    private IncomingInterface incomingFile(String name) {
        return new IncomingInterface(
                CUSTOMER, MESSAGE_TYPE, name, BASE_DIR, BASE_DIR + "/incoming/" + name, Instant.EPOCH
        );
    }

    private ClaimedInterface claimedFile(String name) {
        return new ClaimedInterface(
                CUSTOMER, MESSAGE_TYPE, name, BASE_DIR, BASE_DIR + "/processing/" + name + ".processing"
        );
    }

    private static final class MutableClock extends Clock {
        private Instant current;

        MutableClock(Instant initial) {
            this.current = initial;
        }

        void advance(Duration delta) {
            this.current = this.current.plus(delta);
        }

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return this;
        }

        @Override
        public Instant instant() {
            return current;
        }
    }
}
