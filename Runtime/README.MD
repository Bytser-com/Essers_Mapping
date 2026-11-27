# H.Essers — Generic Runtime Engine (`Runtime`)

The **Runtime** microservice is a Java 21 / Spring Boot 4 backend in the Runtime Stage of the H.Essers Mapping Platform. It fetches customer XML interfaces from `sftp-runtime`, processes them in parallel across multiple Kubernetes replicas without duplicate handling, and exposes operational metrics for Prometheus/Grafana.

---

## Architecture & Multi-Instance Safety

`runtime-backend` runs with **3 to 5 concurrent replicas** in Kubernetes (`readOnlyRootFilesystem: true`) without requiring a shared database or message broker:

1. **Adaptive Drain-Loop (`InterfacePoller` + `SmartLifecycle`):**
   - When `incoming/` is empty, pods sleep for `baseIntervalMs + random(0..maxJitterMs)` (default `5000 ms` + up to `1500 ms` jitter) to prevent synchronized polling spikes (*thundering herd*).
   - When all worker slots are occupied (`WORKERS_BUSY`), the poller **skips SFTP directory scans** and wakes up event-driven as soon as a worker finishes and releases a slot.
   - Implements Spring `SmartLifecycle` at phase `Integer.MAX_VALUE` so polling stops before the SFTP session pool and worker executor shut down.
2. **Bounded Parallel Worker Pool + Backpressure:**
   - Each pod runs up to `RUNTIME_WORKER_CONCURRENCY` (default `4`) parallel Java 21 virtual-thread workers gated by a `Semaphore`.
   - `DefaultSftpSessionFactory(false)` wrapped in `CachingSessionFactory` (`poolSize = max(4, workerConcurrency + 2)`, `testSession = true`) opens dedicated SSH connections across `sftp-runtime` replicas and automatically evicts dead sessions.
   - Transient `RuntimeStorageException` errors during `readBytes()` or `moveToProcessed()` are **not** quarantined into `error/`; only content/validation or size-limit failures move a file to `error/`.
3. **Atomic Claim & POSIX-Safe Stale-Claim Recovery (`SftpRuntimeInterfaceStorage`):**
   - Files are claimed atomically via SFTP `rename` into `processing/<filename>.<claimedEpochMs>.<instanceId>.<token>.processing`. Only one pod can win the kernel-level rename.
   - Stale-claim recovery inspects the embedded `<claimedEpochMs>` timestamp rather than POSIX `mtime` (which SFTP `rename` does not update), preventing active files from being stolen during backlogs longer than `RUNTIME_POLLER_STALE_CLAIM_TIMEOUT_MS` (default `5 min`).
   - XML payloads are streamed in memory with a hard upper bound (`SFTP_RUNTIME_MAX_FILE_SIZE_BYTES`, default `25 MiB`) to prevent OOM poison-pill crash loops while staying compatible with `readOnlyRootFilesystem: true`.
   - Hidden dotfiles (e.g. `.order.xml`), symlinks, and filenames with control characters are ignored; per-customer SFTP errors are isolated so one broken directory cannot block other customers.
4. **Extensible Processing Hook (`InterfaceProcessor`):**
   - US `IT2627T06-56` provides a `@Fallback` `LoggingInterfaceProcessor`. Downstream stories (US `52/53` package lookup, US `152` XML conversion, US `55` delivery) plug directly into `InterfaceProcessor`.

---

## SFTP Folder Layout (`sftp-runtime`)

Under `SFTP_RUNTIME_REMOTE_DIR` (default `/Clients`):

```text
/Clients/
└── <customer>/                  # e.g. nouryon
    └── <message-type>/          # e.g. inbound, outbound
        ├── incoming/            # customer drops .xml files here (ignores .tmp/.part/dotfiles)
        ├── processing/          # atomically claimed: <file>.<epochMs>.<instanceId>.<token>.processing
        ├── processed/           # successfully processed files (collision-safe naming)
        └── error/               # failed files + single-line companion <file>.error.txt
```

---

## Configuration (Environment Variables)

All settings are configured via environment variables (see the root `.env.example`). Never commit real credentials or `.env` files.

| Variable | Default | Description |
|---|---|---|
| `RUNTIME_SERVER_PORT` | `8080` | HTTP port for Actuator health and Prometheus metrics |
| `SFTP_RUNTIME_HOST` | `localhost` | Hostname of `sftp-runtime` |
| `SFTP_RUNTIME_PORT` | `2223` | SFTP port (`22` in Kubernetes, `2223` locally via Docker) |
| `SFTP_RUNTIME_USER` | `runtimeuser` | SFTP username |
| `SFTP_RUNTIME_PASSWORD` | *(empty — set in `.env` / K8s Secret)* | SFTP password (always redacted in logs/toString) |
| `SFTP_RUNTIME_REMOTE_DIR` | `/Clients` | Base directory for customer interfaces |
| `SFTP_ALLOW_UNKNOWN_KEYS` | `false` | Secure-by-default; set `true` in local `.env` or provide `SFTP_KNOWN_HOSTS` |
| `SFTP_KNOWN_HOSTS` | *(empty)* | Optional Spring resource path to SSH `known_hosts` file |
| `SFTP_RUNTIME_CONNECT_TIMEOUT_MS` | `10000` | SSH/SFTP connect & socket timeout in ms |
| `SFTP_RUNTIME_MAX_FILE_SIZE_BYTES` | `26214400` | Max XML payload size in bytes (`25 MiB`); larger files move to `error/` |
| `RUNTIME_POLLER_ENABLED` | `true` | Enable/disable background SFTP polling |
| `RUNTIME_POLLER_BASE_INTERVAL_MS` | `5000` | Idle polling interval when `incoming/` is empty |
| `RUNTIME_POLLER_MAX_JITTER_MS` | `1500` | Maximum random jitter added to idle/recovery delays (`0` disables) |
| `RUNTIME_POLLER_MIN_FILE_AGE_MS` | `3000` | Minimum file age before claiming (avoids partial uploads) |
| `RUNTIME_WORKER_CONCURRENCY` | `4` | Max parallel XML workers per pod |
| `RUNTIME_POLLER_STALE_CLAIM_TIMEOUT_MS` | `300000` | Claim age after which stuck `processing/` files return to `incoming/` |
| `RUNTIME_POLLER_STALE_RECOVERY_INTERVAL_MS` | `60000` | Interval for stale-claim recovery scans |
| `RUNTIME_POLLER_SHUTDOWN_AWAIT_SECONDS` | `20` | Graceful worker drain timeout on shutdown (kept below K8s 30s grace period) |

---

## Observability & Prometheus Metrics

Spring Boot Actuator exposes `/actuator/health`, `/actuator/health/readiness`, `/actuator/health/liveness`, and `/actuator/prometheus`:

- `runtime_sftp_backlog_files` — Gauge of ready XML files waiting in `incoming/` (**aggregate across replicas with `max(runtime_sftp_backlog_files)`**, never `sum()`, because every pod observes the shared SFTP backlog).
- `runtime_workers_active` — Gauge of active parallel workers in the pod.
- `runtime_files_processed_total` — Counter of successfully processed interfaces.
- `runtime_files_failed_total` — Counter of failed interfaces moved to `error/`.
- `runtime_poller_errors_total` — Counter of failed SFTP poll or stale-recovery cycles.
- `runtime_file_processing_duration_seconds` — Timer recording end-to-end processing latency per claimed file.

### Kubernetes Infra Alignment Notes

When deploying `Runtime` to Testing/Production, ensure the Kubernetes manifests are aligned on these 4 items:
1. Set `SFTP_RUNTIME_REMOTE_DIR=/Clients` in `common-config` (matching `sftp-runtime` `home_dir: /srv/sftpgo/data`).
2. Configure `SFTP_KNOWN_HOSTS` (recommended) or explicitly set `SFTP_ALLOW_UNKNOWN_KEYS=true` while `sftp-runtime` host keys are dynamically generated on PVC.
3. Add a Prometheus `ServiceMonitor` endpoint targeting `runtime-backend` on `/actuator/prometheus` (currently `essers-mapping-servicemonitor.yaml` only scrapes the Python services on `/metrics`).
4. Optionally switch `runtime-backend` probes from `tcpSocket` to HTTP `/actuator/health/readiness` and `/actuator/health/liveness`.

---

## Running & Testing Locally

```bash
# 1. Start local SFTPGo containers (from repository root)
docker compose -f Scripts/docker-compose.sftp.yml up -d

# 2. Load your local .env (never committed)
source .env

# 3. Run unit, embedded SSHD integration, and JaCoCo checks
cd Runtime
bash ./mvnw clean verify

# 4. Run the service locally
bash ./mvnw spring-boot:run
```
