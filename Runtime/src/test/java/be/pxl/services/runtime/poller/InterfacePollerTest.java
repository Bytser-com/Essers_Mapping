package be.pxl.services.runtime.poller;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledFuture;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.scheduling.TaskScheduler;

import be.pxl.services.runtime.config.RuntimePollerProperties;
import be.pxl.services.runtime.domain.ClaimedInterface;
import be.pxl.services.runtime.domain.IncomingInterface;
import be.pxl.services.runtime.exception.RuntimeStorageException;
import be.pxl.services.runtime.metrics.RuntimeMetrics;
import be.pxl.services.runtime.poller.InterfacePoller.DrainOutcome;
import be.pxl.services.runtime.processor.InterfaceProcessor;
import be.pxl.services.runtime.storage.RuntimeInterfaceStorage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
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
    private InterfacePoller poller;

    @BeforeEach
    void setUp() {
        storage = mock(RuntimeInterfaceStorage.class);
        processor = mock(InterfaceProcessor.class);
        taskScheduler = mock(TaskScheduler.class);
        workerExecutor = Executors.newSingleThreadExecutor();
        meterRegistry = new SimpleMeterRegistry();
        metrics = new RuntimeMetrics(meterRegistry);
        poller = new InterfacePoller(storage, processor, defaultProperties(1_500L), metrics, taskScheduler, workerExecutor);
    }

    @AfterEach
    void tearDown() {
        poller.stop();
        workerExecutor.shutdownNow();
    }

    @Test
    @DisplayName("drainOnce claims, processes, moves file to processed/ and updates metrics")
    void drainOnceProcessesClaimedFileAndUpdatesMetrics() {
        IncomingInterface incoming = incomingFile("order_1.xml");
        ClaimedInterface claimed = claimedFile("order_1.xml");

        when(storage.listReadyIncoming(Duration.ofMillis(3_000L))).thenReturn(List.of(incoming));
        when(storage.tryClaim(incoming, INSTANCE_ID)).thenReturn(Optional.of(claimed));
        when(storage.readBytes(claimed)).thenReturn(SAMPLE_XML);

        DrainOutcome outcome = poller.drainOnce();
        poller.stop();

        assertEquals(DrainOutcome.DRAINED, outcome);
        verify(processor).process(claimed, SAMPLE_XML);
        verify(storage).moveToProcessed(claimed);
        assertEquals(1, metrics.backlogCount());
        assertEquals(0, metrics.activeWorkers());
        assertEquals(1.0, meterRegistry.get(RuntimeMetrics.FILES_PROCESSED_METRIC).counter().count());
        assertEquals(0.0, meterRegistry.get(RuntimeMetrics.FILES_FAILED_METRIC).counter().count());
    }

    @Test
    @DisplayName("drainOnce skips files already claimed by another pod without calling processor")
    void drainOnceSkipsAlreadyClaimedFile() {
        IncomingInterface incoming = incomingFile("order_1.xml");
        when(storage.listReadyIncoming(any())).thenReturn(List.of(incoming));
        when(storage.tryClaim(incoming, INSTANCE_ID)).thenReturn(Optional.empty());

        DrainOutcome outcome = poller.drainOnce();

        assertEquals(DrainOutcome.IDLE, outcome);
        verify(storage, never()).readBytes(any());
        verify(processor, never()).process(any(), any());
    }

    @Test
    @DisplayName("drainOnce isolates processing errors so remaining files still succeed")
    void drainOnceIsolatesFailuresPerFile() {
        IncomingInterface badIncoming = incomingFile("bad.xml");
        IncomingInterface goodIncoming = incomingFile("good.xml");
        ClaimedInterface badClaimed = claimedFile("bad.xml");
        ClaimedInterface goodClaimed = claimedFile("good.xml");

        when(storage.listReadyIncoming(any())).thenReturn(List.of(badIncoming, goodIncoming));
        when(storage.tryClaim(badIncoming, INSTANCE_ID)).thenReturn(Optional.of(badClaimed));
        when(storage.tryClaim(goodIncoming, INSTANCE_ID)).thenReturn(Optional.of(goodClaimed));
        when(storage.readBytes(badClaimed)).thenReturn(SAMPLE_XML);
        when(storage.readBytes(goodClaimed)).thenReturn(SAMPLE_XML);
        doThrow(new IllegalArgumentException("Interface is geen geldig XML"))
                .when(processor).process(eq(badClaimed), any());

        DrainOutcome outcome = poller.drainOnce();
        poller.stop();

        assertEquals(DrainOutcome.DRAINED, outcome);
        verify(storage).moveToError(badClaimed, "Interface is geen geldig XML");
        verify(storage).moveToProcessed(goodClaimed);
        assertEquals(1.0, meterRegistry.get(RuntimeMetrics.FILES_FAILED_METRIC).counter().count());
        assertEquals(1.0, meterRegistry.get(RuntimeMetrics.FILES_PROCESSED_METRIC).counter().count());
    }

    @Test
    @DisplayName("nextDelayMs drains immediately on backlog and applies jitter only while idle")
    void nextDelayUsesDrainLoopAndIdleJitter() {
        assertEquals(0L, poller.nextDelayMs(DrainOutcome.DRAINED));
        assertEquals(InterfacePoller.BUSY_RETRY_DELAY_MS, poller.nextDelayMs(DrainOutcome.WORKERS_BUSY));

        for (int i = 0; i < 25; i++) {
            long idleDelay = poller.nextDelayMs(DrainOutcome.IDLE);
            assertTrue(idleDelay >= 5_000L && idleDelay <= 6_500L,
                    "Expected idle delay in [5000, 6500], got " + idleDelay);
        }

        InterfacePoller zeroJitterPoller = new InterfacePoller(
                storage, processor, defaultProperties(0L), metrics, taskScheduler, workerExecutor);
        assertEquals(5_000L, zeroJitterPoller.computeIdleDelayMs());
    }

    @Test
    @DisplayName("pollAndReschedule keeps rescheduling even after temporary SFTP outage")
    void pollAndRescheduleSurvivesStorageOutage() {
        ScheduledFuture<?> future = mock(ScheduledFuture.class);
        when(taskScheduler.schedule(any(Runnable.class), any(Instant.class))).thenAnswer(inv -> future);
        when(storage.listReadyIncoming(any())).thenThrow(new RuntimeStorageException("SFTP offline"));

        poller.start();
        poller.pollAndReschedule();
        poller.stop();

        verify(taskScheduler, times(3)).schedule(any(Runnable.class), any(Instant.class));
        verify(future, times(2)).cancel(false);
    }

    @Test
    @DisplayName("recoverStaleOnce delegates timeout to storage")
    void recoverStaleOnceDelegatesToStorage() {
        when(storage.recoverStaleClaims(Duration.ofMillis(300_000L))).thenReturn(2);

        assertEquals(2, poller.recoverStaleOnce());
        verify(storage).recoverStaleClaims(Duration.ofMillis(300_000L));
    }

    private RuntimePollerProperties defaultProperties(long maxJitterMs) {
        return new RuntimePollerProperties(
                true, 5_000L, maxJitterMs, 3_000L, 4, 300_000L, 60_000L, 5, INSTANCE_ID
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
}
