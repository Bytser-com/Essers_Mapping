# H.Essers — Generic Runtime Engine (`Runtime`)

The **Runtime** microservice is a Java 21 / Spring Boot 4 backend in the Runtime Stage of the H.Essers Mapping Platform. It fetches customer XML interfaces from `sftp-runtime`, processes them in parallel across multiple Kubernetes replicas without duplicate handling, and exposes operational metrics for Prometheus/Grafana.

---

## Architecture & Multi-Instance Safety

`runtime-backend` runs with **3 to 5 concurrent replicas** in Kubernetes (`readOnlyRootFilesystem: true`) without requiring a shared database or message broker:

1. **Adaptive Drain-Loop (`InterfacePoller`):**
   - When `incoming/` is empty, pods sleep for `baseIntervalMs + random(0..maxJitterMs)` (default `5000 ms` + up to `1500 ms` jitter) to prevent synchronized polling spikes (*thundering herd*) after batches or SFTP restarts.
   - Whenever backlog exists, pods immediately drain files without idle sleeps.
2. **Bounded Parallel Worker Pool + Backpressure:**
   - Each pod runs up to `RUNTIME_WORKER_CONCURRENCY` (default `4`) parallel Java 21 virtual-thread workers gated by a `Semaphore`.
   - A file is claimed from SFTP **only** when a worker slot is available, keeping memory usage bounded regardless of SFTP backlog size.
   - `CachingSessionFactory` is sized to `max(4, workerConcurrency + 2)` so parallel workers do not contend on a single SFTP session.
3. **Atomic Claim & Stale-Claim Recovery (`SftpRuntimeInterfaceStorage`):**
   - Files are claimed atomically via SFTP `rename` into `processing/<filename>.<instanceId>.<token>.processing`. Only one pod can win the kernel-level rename.
   - XML payloads are streamed in memory (`byte[]`), matching Kubernetes `readOnlyRootFilesystem: true`.
   - Stale `.processing` files older than `RUNTIME_POLLER_STALE_CLAIM_TIMEOUT_MS` (default `5 min`) are automatically returned to `incoming/` if a pod crashes mid-flight.
4. **Extensible Processing Hook (`InterfaceProcessor`):**
   - US `IT2627T06-56` provides a `@Fallback` `LoggingInterfaceProcessor`. Downstream stories (US `52/53` package lookup, US `152` XML conversion, US `55` delivery) plug directly into `InterfaceProcessor`.

---

## SFTP Folder Layout (`sftp-runtime`)

Under `SFTP_RUNTIME_REMOTE_DIR` (default `/Clients`):

```text
/Clients/
└── <customer>/                  # e.g. nouryon
    └── <message-type>/          # e.g. inbound, outbound
        ├── incoming/            # customer drops .xml files here (ignores .tmp/.part)
        ├── processing/          # atomically claimed by one pod
        ├── processed/           # successfully processed files
        └── error/               # failed files + companion <file>.error.txt
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
| `SFTP_RUNTIME_PASSWORD` | *(empty — set in `.env` / K8s Secret)* | SFTP password |
| `SFTP_RUNTIME_REMOTE_DIR` | `/Clients` | Base directory for customer interfaces |
| `SFTP_ALLOW_UNKNOWN_KEYS` | `true` | Allow unknown SSH host keys in local/dev environments |
| `RUNTIME_POLLER_ENABLED` | `true` | Enable/disable background SFTP polling |
| `RUNTIME_POLLER_BASE_INTERVAL_MS` | `5000` | Idle polling interval when `incoming/` is empty |
| `RUNTIME_POLLER_MAX_JITTER_MS` | `1500` | Maximum random jitter added to idle/recovery delays (`0` disables) |
| `RUNTIME_POLLER_MIN_FILE_AGE_MS` | `3000` | Minimum file age before claiming (avoids partial uploads) |
| `RUNTIME_WORKER_CONCURRENCY` | `4` | Max parallel XML workers per pod |
| `RUNTIME_POLLER_STALE_CLAIM_TIMEOUT_MS` | `300000` | Age after which stuck `processing/` claims return to `incoming/` |
| `RUNTIME_POLLER_STALE_RECOVERY_INTERVAL_MS` | `60000` | Interval for stale-claim recovery scans |

---

## Observability & Prometheus Metrics

Spring Boot Actuator exposes `/actuator/health` and `/actuator/prometheus` (scraped automatically every 15s by `essers-mapping-servicemonitor.yaml`):

- `runtime_sftp_backlog_files` — Gauge of ready XML files currently waiting in `incoming/` (ready for Grafana alerts and KEDA / Custom Metrics HPA autoscaling).
- `runtime_workers_active` — Gauge of active parallel workers in the pod.
- `runtime_files_processed_total` — Counter of successfully processed interfaces.
- `runtime_files_failed_total` — Counter of failed interfaces moved to `error/`.

---

## Running & Testing Locally

```bash
# 1. Start local SFTPGo containers (from repository root)
docker compose -f Scripts/docker-compose.sftp.yml up -d

# 2. Load your local .env (never committed)
source .env

# 3. Run unit, integration, and JaCoCo checks
cd Runtime
bash ./mvnw clean verify

# 4. Run the service locally
bash ./mvnw spring-boot:run
```
