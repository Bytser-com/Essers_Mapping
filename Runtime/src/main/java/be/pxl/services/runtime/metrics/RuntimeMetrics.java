package be.pxl.services.runtime.metrics;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

/**
 * Micrometer metrics exposed via {@code /actuator/prometheus} for Grafana dashboards
 * and backlog-based Kubernetes autoscaling (KEDA / Custom Metrics HPA).
 */
@Component
public class RuntimeMetrics {

    public static final String BACKLOG_FILES_METRIC = "runtime.sftp.backlog.files";
    public static final String ACTIVE_WORKERS_METRIC = "runtime.workers.active";
    public static final String FILES_PROCESSED_METRIC = "runtime.files.processed";
    public static final String FILES_FAILED_METRIC = "runtime.files.failed";
    public static final String POLL_ERRORS_METRIC = "runtime.poller.errors";
    public static final String STORAGE_ERRORS_METRIC = "runtime.storage.errors";
    public static final String PROCESSING_DURATION_METRIC = "runtime.file.processing.duration";

    private final AtomicInteger backlogFiles = new AtomicInteger(0);
    private final AtomicInteger activeWorkers = new AtomicInteger(0);
    private final Counter filesProcessed;
    private final Counter filesFailed;
    private final Counter pollErrors;
    private final Counter storageErrors;
    private final Timer processingDuration;

    public RuntimeMetrics(MeterRegistry meterRegistry) {
        Gauge.builder(BACKLOG_FILES_METRIC, backlogFiles, AtomicInteger::get)
                .description("Current number of ready incoming XML files waiting on sftp-runtime (use max() across replicas)")
                .register(meterRegistry);

        Gauge.builder(ACTIVE_WORKERS_METRIC, activeWorkers, AtomicInteger::get)
                .description("Current number of active parallel interface workers in this pod")
                .register(meterRegistry);

        this.filesProcessed = Counter.builder(FILES_PROCESSED_METRIC)
                .description("Total number of customer XML interfaces processed successfully")
                .register(meterRegistry);

        this.filesFailed = Counter.builder(FILES_FAILED_METRIC)
                .description("Total number of customer XML interfaces that failed and moved to error/")
                .register(meterRegistry);

        this.pollErrors = Counter.builder(POLL_ERRORS_METRIC)
                .description("Total number of failed SFTP poll or stale-recovery cycles")
                .register(meterRegistry);

        this.storageErrors = Counter.builder(STORAGE_ERRORS_METRIC)
                .description("Total number of transient SFTP storage errors in workers during read or moveToProcessed")
                .register(meterRegistry);

        this.processingDuration = Timer.builder(PROCESSING_DURATION_METRIC)
                .description("End-to-end processing duration per claimed customer XML interface")
                .register(meterRegistry);
    }

    public void setBacklogCount(int count) {
        backlogFiles.set(Math.max(0, count));
    }

    public int backlogCount() {
        return backlogFiles.get();
    }

    public void workerStarted() {
        activeWorkers.incrementAndGet();
    }

    public void workerFinished() {
        activeWorkers.updateAndGet(current -> Math.max(0, current - 1));
    }

    public int activeWorkers() {
        return activeWorkers.get();
    }

    public void recordProcessed() {
        filesProcessed.increment();
    }

    public void recordFailed() {
        filesFailed.increment();
    }

    public void recordPollError() {
        pollErrors.increment();
    }

    public void recordStorageError() {
        storageErrors.increment();
    }

    public void recordProcessingDuration(long durationNanos) {
        if (durationNanos >= 0) {
            processingDuration.record(durationNanos, TimeUnit.NANOSECONDS);
        }
    }
}
