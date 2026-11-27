package be.pxl.services.runtime.metrics;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RuntimeMetricsTest {

    @Test
    @DisplayName("RuntimeMetrics tracks backlog gauge, active workers and processed/failed counters")
    void tracksGaugesAndCounters() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        RuntimeMetrics metrics = new RuntimeMetrics(registry);

        metrics.setBacklogCount(12);
        metrics.workerStarted();
        metrics.workerStarted();
        metrics.recordProcessed();
        metrics.recordFailed();
        metrics.workerFinished();

        assertEquals(12, metrics.backlogCount());
        assertEquals(1, metrics.activeWorkers());
        assertEquals(12.0, registry.get(RuntimeMetrics.BACKLOG_FILES_METRIC).gauge().value());
        assertEquals(1.0, registry.get(RuntimeMetrics.ACTIVE_WORKERS_METRIC).gauge().value());
        assertEquals(1.0, registry.get(RuntimeMetrics.FILES_PROCESSED_METRIC).counter().count());
        assertEquals(1.0, registry.get(RuntimeMetrics.FILES_FAILED_METRIC).counter().count());

        // Guards against negative counts
        metrics.setBacklogCount(-3);
        metrics.workerFinished();
        metrics.workerFinished();
        assertEquals(0, metrics.backlogCount());
        assertEquals(0, metrics.activeWorkers());
    }
}
