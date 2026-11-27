package be.pxl.services.runtime.metrics;

import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
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

    private final AtomicInteger backlogFiles = new AtomicInteger(0);
    private final AtomicInteger activeWorkers = new AtomicInteger(0);
    private final Counter filesProcessed;
    private final Counter filesFailed;

    public RuntimeMetrics(MeterRegistry meterRegistry) {
        Gauge.builder(BACKLOG_FILES_METRIC, backlogFiles, AtomicInteger::get)
                .description("Current number of ready incoming XML files waiting on sftp-runtime")
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
}
