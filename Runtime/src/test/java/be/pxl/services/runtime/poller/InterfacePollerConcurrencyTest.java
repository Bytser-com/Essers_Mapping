package be.pxl.services.runtime.poller;

import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

import be.pxl.services.runtime.config.RuntimePollerProperties;
import be.pxl.services.runtime.domain.ClaimedInterface;
import be.pxl.services.runtime.domain.IncomingInterface;
import be.pxl.services.runtime.metrics.RuntimeMetrics;
import be.pxl.services.runtime.poller.InterfacePoller.DrainOutcome;
import be.pxl.services.runtime.processor.InterfaceProcessor;
import be.pxl.services.runtime.storage.RuntimeInterfaceStorage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;

class InterfacePollerConcurrencyTest {

    private static final String CUSTOMER = "nouryon";
    private static final String MESSAGE_TYPE = "outbound";
    private static final String BASE_DIR = "/Clients/nouryon/outbound";

    @Test
    @DisplayName("Bounded worker pool fills exact concurrency deterministically and skips scans while busy")
    void boundedWorkerPoolEnforcesConcurrencyLimit() throws Exception {
        int fileCount = 12;
        int maxConcurrency = 3;
        InMemoryAtomicStorage storage = new InMemoryAtomicStorage(fileCount);
        AtomicInteger active = new AtomicInteger(0);
        AtomicInteger maxObserved = new AtomicInteger(0);
        CountDownLatch firstWaveStarted = new CountDownLatch(maxConcurrency);
        CountDownLatch releaseFirstWave = new CountDownLatch(1);
        CountDownLatch allProcessed = new CountDownLatch(fileCount);

        InterfaceProcessor processor = (claimed, xml) -> {
            int current = active.incrementAndGet();
            maxObserved.accumulateAndGet(current, Math::max);
            try {
                firstWaveStarted.countDown();
                releaseFirstWave.await(5, TimeUnit.SECONDS);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } finally {
                active.decrementAndGet();
                allProcessed.countDown();
            }
        };

        ExecutorService virtualExecutor = Executors.newVirtualThreadPerTaskExecutor();
        RuntimeMetrics metrics = new RuntimeMetrics(new SimpleMeterRegistry());
        RuntimePollerProperties props = new RuntimePollerProperties(
                true, 5_000L, 0L, 0L, maxConcurrency, 300_000L, 60_000L, 10, "pod-bounded"
        );
        InterfacePoller poller = new InterfacePoller(
                storage, processor, props, metrics, mock(TaskScheduler.class), virtualExecutor, Clock.systemUTC());

        try {
            assertEquals(DrainOutcome.WORKERS_BUSY, poller.drainOnce());
            assertTrue(firstWaveStarted.await(5, TimeUnit.SECONDS), "First wave should fill all worker slots");
            int scansBeforeBusyCheck = storage.listCalls();
            assertEquals(DrainOutcome.WORKERS_BUSY, poller.drainOnce());
            assertEquals(scansBeforeBusyCheck, storage.listCalls(), "WORKERS_BUSY must not scan SFTP");

            releaseFirstWave.countDown();
            while (!storage.isEmpty()) {
                if (poller.drainOnce() == DrainOutcome.WORKERS_BUSY) {
                    storage.awaitProgress(100);
                }
            }
            assertTrue(allProcessed.await(10, TimeUnit.SECONDS), "All files should finish processing");
            poller.stop();
        } finally {
            releaseFirstWave.countDown();
            virtualExecutor.shutdownNow();
        }

        assertEquals(maxConcurrency, maxObserved.get(), "Expected exact configured concurrency");
        assertEquals(fileCount, storage.processedCount());
        assertEquals(0, storage.errorCount());
        assertEquals(0, metrics.activeWorkers());
    }

    @Test
    @DisplayName("Real ThreadPoolTaskScheduler drains full backlog via event-driven worker wakeups without races")
    void realTaskSchedulerDrainsBacklogViaEventDrivenWakeups() throws Exception {
        int fileCount = 24;
        int concurrency = 3;
        InMemoryAtomicStorage storage = new InMemoryAtomicStorage(fileCount);
        CountDownLatch allProcessed = new CountDownLatch(fileCount);
        InterfaceProcessor processor = (claimed, xml) -> allProcessed.countDown();

        ThreadPoolTaskScheduler realScheduler = new ThreadPoolTaskScheduler();
        realScheduler.setPoolSize(2);
        realScheduler.setThreadNamePrefix("test-poller-");
        realScheduler.initialize();
        ExecutorService virtualExecutor = Executors.newVirtualThreadPerTaskExecutor();
        RuntimeMetrics metrics = new RuntimeMetrics(new SimpleMeterRegistry());
        RuntimePollerProperties props = new RuntimePollerProperties(
                true, 50L, 0L, 0L, concurrency, 300_000L, 60_000L, 5, "pod-scheduler"
        );
        InterfacePoller poller = new InterfacePoller(
                storage, processor, props, metrics, realScheduler, virtualExecutor, Clock.systemUTC());

        try {
            poller.start();
            assertTrue(allProcessed.await(10, TimeUnit.SECONDS),
                    "Event-driven wakeups on real ThreadPoolTaskScheduler must drain all files cleanly");
            poller.stop();
        } finally {
            realScheduler.shutdown();
            virtualExecutor.shutdownNow();
        }

        assertEquals(fileCount, storage.processedCount());
        assertEquals(0, storage.errorCount());
        assertEquals(0, metrics.activeWorkers());
    }

    @Test
    @DisplayName("5 pods x 4 workers racing on 50 files process every file exactly once with zero duplicates")
    void multiplePodsClaimAndProcessEveryFileExactlyOnce() throws Exception {
        int fileCount = 50;
        int podCount = 5;
        int workersPerPod = 4;
        InMemoryAtomicStorage storage = new InMemoryAtomicStorage(fileCount);
        AtomicInteger totalInvocations = new AtomicInteger(0);
        Set<String> processedNames = ConcurrentHashMap.newKeySet();

        InterfaceProcessor processor = (claimed, xml) -> {
            totalInvocations.incrementAndGet();
            processedNames.add(claimed.filename());
        };

        CountDownLatch startGate = new CountDownLatch(1);
        CountDownLatch podsFinished = new CountDownLatch(podCount);
        List<ExecutorService> executors = new ArrayList<>();
        ExecutorService podRunner = Executors.newFixedThreadPool(podCount);

        try {
            for (int i = 1; i <= podCount; i++) {
                ExecutorService workerExec = Executors.newVirtualThreadPerTaskExecutor();
                executors.add(workerExec);
                RuntimePollerProperties props = new RuntimePollerProperties(
                        true, 5_000L, 500L, 0L, workersPerPod, 300_000L, 60_000L, 10, "pod-" + i
                );
                InterfacePoller podPoller = new InterfacePoller(
                        storage, processor, props, new RuntimeMetrics(new SimpleMeterRegistry()),
                        mock(TaskScheduler.class), workerExec, Clock.systemUTC());

                podRunner.execute(() -> {
                    try {
                        startGate.await();
                        while (!storage.isEmpty()) {
                            if (podPoller.drainOnce() == DrainOutcome.WORKERS_BUSY) {
                                storage.awaitProgress(50);
                            }
                        }
                        podPoller.stop();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    } finally {
                        podsFinished.countDown();
                    }
                });
            }

            startGate.countDown();
            assertTrue(podsFinished.await(15, TimeUnit.SECONDS), "All 5 pods should finish draining");
        } finally {
            podRunner.shutdownNow();
            executors.forEach(ExecutorService::shutdownNow);
        }

        assertEquals(fileCount, totalInvocations.get(), "Each file must be processed exactly once");
        assertEquals(fileCount, processedNames.size(), "All distinct files must be processed");
        assertEquals(fileCount, storage.processedCount());
        assertEquals(0, storage.errorCount());
    }

    @Test
    @DisplayName("stop() respects a single shared shutdown deadline when a worker is stuck")
    void stopTimesOutGracefullyWithinSingleDeadline() throws Exception {
        InMemoryAtomicStorage storage = new InMemoryAtomicStorage(1);
        CountDownLatch workerRunning = new CountDownLatch(1);
        CountDownLatch releaseWorker = new CountDownLatch(1);
        InterfaceProcessor stuckProcessor = (claimed, xml) -> {
            workerRunning.countDown();
            try {
                releaseWorker.await(5, TimeUnit.SECONDS);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        };

        ExecutorService virtualExecutor = Executors.newVirtualThreadPerTaskExecutor();
        RuntimePollerProperties props = new RuntimePollerProperties(
                true, 5_000L, 0L, 0L, 1, 300_000L, 60_000L, 1, "pod-timeout"
        );
        InterfacePoller poller = new InterfacePoller(
                storage, stuckProcessor, props, new RuntimeMetrics(new SimpleMeterRegistry()),
                mock(TaskScheduler.class), virtualExecutor, Clock.systemUTC());

        try {
            poller.drainOnce();
            assertTrue(workerRunning.await(5, TimeUnit.SECONDS));
            long startMs = System.currentTimeMillis();
            poller.stop();
            long elapsedMs = System.currentTimeMillis() - startMs;
            assertTrue(elapsedMs < 2_500L, "Shared shutdown deadline should not double-wait; took " + elapsedMs + "ms");
            assertEquals(1, storage.processingCount());
        } finally {
            releaseWorker.countDown();
            virtualExecutor.shutdownNow();
        }
    }

    private static final class InMemoryAtomicStorage implements RuntimeInterfaceStorage {

        private final Map<String, byte[]> incoming = new ConcurrentHashMap<>();
        private final Map<String, byte[]> processing = new ConcurrentHashMap<>();
        private final Set<String> processed = ConcurrentHashMap.newKeySet();
        private final Set<String> errors = ConcurrentHashMap.newKeySet();
        private final AtomicInteger listCounter = new AtomicInteger(0);
        private final Object progressMonitor = new Object();

        InMemoryAtomicStorage(int fileCount) {
            for (int i = 1; i <= fileCount; i++) {
                String name = "order_" + i + ".xml";
                incoming.put(name, ("<order id=\"" + i + "\"/>").getBytes(StandardCharsets.UTF_8));
            }
        }

        boolean isEmpty() {
            return incoming.isEmpty();
        }

        int listCalls() {
            return listCounter.get();
        }

        int processingCount() {
            return processing.size();
        }

        int processedCount() {
            return processed.size();
        }

        int errorCount() {
            return errors.size();
        }

        void awaitProgress(long timeoutMs) throws InterruptedException {
            synchronized (progressMonitor) {
                if (!incoming.isEmpty()) {
                    progressMonitor.wait(timeoutMs);
                }
            }
        }

        private void notifyProgress() {
            synchronized (progressMonitor) {
                progressMonitor.notifyAll();
            }
        }

        @Override
        public List<IncomingInterface> listReadyIncoming(Duration minFileAge) {
            listCounter.incrementAndGet();
            return incoming.keySet().stream()
                    .sorted()
                    .map(name -> new IncomingInterface(
                            CUSTOMER, MESSAGE_TYPE, name, BASE_DIR, BASE_DIR + "/incoming/" + name, Instant.EPOCH))
                    .toList();
        }

        @Override
        public Optional<ClaimedInterface> tryClaim(IncomingInterface candidate, String instanceId) {
            byte[] payload = incoming.remove(candidate.filename());
            if (payload == null) {
                return Optional.empty();
            }
            String claimedPath = BASE_DIR + "/processing/" + candidate.filename() + "." + instanceId + ".processing";
            processing.put(claimedPath, payload);
            notifyProgress();
            return Optional.of(new ClaimedInterface(
                    candidate.customer(), candidate.messageType(), candidate.filename(), BASE_DIR, claimedPath));
        }

        @Override
        public byte[] readBytes(ClaimedInterface claimed) {
            return processing.getOrDefault(claimed.claimedPath(), new byte[0]);
        }

        @Override
        public void moveToProcessed(ClaimedInterface claimed) {
            processing.remove(claimed.claimedPath());
            processed.add(claimed.filename());
            notifyProgress();
        }

        @Override
        public void moveToError(ClaimedInterface claimed, String reason) {
            processing.remove(claimed.claimedPath());
            errors.add(claimed.filename());
            notifyProgress();
        }

        @Override
        public int recoverStaleClaims(Duration maxAge) {
            return 0;
        }
    }
}
