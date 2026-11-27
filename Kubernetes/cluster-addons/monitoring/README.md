# Kubernetes Monitoring, Dashboards & Discord Alerting (`IT2627T06-164`)

Declarative, GitOps-managed observability stack for **Essers Mapping** across the **Testing** and **Production** MiniPC Kubernetes clusters using **Prometheus Operator (`kube-prometheus-stack`)**, **Grafana**, **Alertmanager (Discord)**, **Loki**, **Grafana Alloy**, and **Calico Zero-Trust NetworkPolicies**.

---

## 1. Architecture & Reachability

```text
                                        [ MetalLB / Cloudflare Tunnel ]
                       Testing: 192.168.100.101 | Production: 192.168.100.201
                                                  │
                                                  ▼
                                      ┌───────────────────────┐
                                      │  NGINX Ingress (443)  │ (metrics :10254)
                                      └───────────┬───────────┘
                                                  │
                                                  ▼
               ┌────────────────────────────────────────────────────────────────────┐
               │                         MONITORING NAMESPACE                       │
               │                                                                    │
               │  ┌─────────────────┐   PromQL/LogQL   ┌─────────────────────────┐  │
               │  │     Grafana     │ ───────────────► │  Prometheus (:9090)     │  │
               │  │     (:3000)     │ ───────────────► │  Loki       (:3100)     │  │
               │  └────────┬────────┘                  └────────────┬────────────┘  │
               │           │ GitOps sidecar                         │ Alerts (:9093)│
               │           ▼                                        ▼               │
               │  ┌─────────────────┐                  ┌─────────────────────────┐  │
               │  │  3 Dashboards   │                  │ Alertmanager -> Discord │  │
               │  │  (ConfigMaps)   │                  └─────────────────────────┘  │
               │  └─────────────────┘                                               │
               └────────────────────────────────────────────────────┬───────────────┘
                                                                    │ Scrapes / Remote-Write
            ┌───────────────────────────────┬───────────────────────┴──────────────────────┐
            ▼                               ▼                                              ▼
┌────────────────────────┐     ┌───────────────────────────┐     ┌──────────────────────────────────┐
│ Kubelet/cAdvisor :10250│     │ Node Exporter + Alloy VMs │     │ Essers App Metrics (/metrics)    │
│ kube-state-metrics     │     │ (Host CPU/RAM/Disk/Logs)  │     │ mapping-proposal & converter     │
│ CoreDNS & API Server   │     │ ingress-nginx :10254      │     │ (Proposals, AI runs, SFTP, queue)│
└────────────────────────┘     └───────────────────────────┘     └──────────────────────────────────┘
```

### Administrator Endpoints

| Component | Testing | Production |
| :--- | :--- | :--- |
| **Grafana UI (Public/Tunnel)** | `https://monitor-testing.shystack.com` | `https://monitor-production.shystack.com` |
| **Grafana UI (LAN Ingress)** | `https://grafana.testing.essers.local` (`192.168.100.101`) | `https://grafana.essers.example.com` (`192.168.100.201`) |
| **Prometheus UI (Admin Port-Forward)** | `kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090` | `kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090` |
| **Alertmanager UI (Admin Port-Forward)** | `kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093` | `kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093` |

### Prometheus Scrape Targets

Prometheus scrapes the following targets with `cluster="testing"` or `cluster="production"` attached via `metricRelabelings` / `relabelings`:

* **Kubernetes & Pods:** `kubelet` (`/metrics` & `/metrics/cadvisor`), `kube-state-metrics`, `kube-apiserver`, `coredns`.
* **Host / MiniPC VMs:** `node-exporter` pushed via Grafana Alloy (`remote_write`) with `cluster` and `environment` labels.
* **Ingress:** `ingress-nginx` controller metrics (`port 10254`, enabled via `controller.metrics.enabled: true`).
* **Essers Application Metrics:** `mapping-proposal` (`:8000/metrics`) and `mapping-converter` (`:8000/metrics`).
* **Self-monitoring:** `prometheus`, `alertmanager`.

> **Intentionally disabled targets (to keep `/targets` 100% UP):**
> * `kubeEtcd`, `kubeControllerManager`, `kubeScheduler`, `kubeProxy`: kubeadm binds these control-plane daemons to `127.0.0.1` by default, so scraping them remotely causes permanent `DOWN` targets.
> * `frontend`, `version-control-backend`, `runtime-backend`, `sftp-shared`, `sftp-runtime`: these services do not expose `/metrics` or `/actuator/prometheus` today and are monitored via cAdvisor, `kube-state-metrics`, Longhorn PVC metrics, and Loki container logs.

---

## 2. Pod Metrics & Documented Fallbacks (`TC-164-01`)

| Resource Category | Primary Pod Metric (PromQL Source) | Availability on Debian 13 / `containerd` (cgroup v2) | Documented Fallback / Alternative |
| :--- | :--- | :--- | :--- |
| **Pod CPU** | `container_cpu_usage_seconds_total` (cAdvisor) + `kube_pod_container_resource_requests/limits` | **Available** for all running pods (`0` is valid for idle pods). | — |
| **Pod RAM** | `container_memory_working_set_bytes` (cAdvisor) + `kube_pod_container_resource_requests/limits` | **Available** for all running pods. | — |
| **Pod Network (RX/TX)** | `container_network_receive_bytes_total`, `container_network_transmit_bytes_total` (`interface!="lo"`) | **Available** via cAdvisor on the pod network namespace (pause/sandbox container — queries intentionally do **not** exclude `container="POD"`). | Node network metrics from `node-exporter` if a pod uses `hostNetwork`. |
| **Pod Disk I/O** | `container_fs_reads_bytes_total`, `container_fs_writes_bytes_total` | **Often missing or `0`** on `containerd` + `overlayfs` + `cgroup v2` because container-level overlay block accounting is not exposed uniformly per pod. | **1. Volume metrics (PVC):** `kubelet_volume_stats_used_bytes` & `kubelet_volume_stats_capacity_bytes` (Longhorn PVCs).<br>**2. Node disk metrics:** `node_disk_read_bytes_total`, `node_disk_written_bytes_total`, and `node_filesystem_avail_bytes` / `node_filesystem_size_bytes` via `node-exporter`. |

---

## 3. Dashboard Filtering (`TC-164-02`)

All dashboards expose cascading Grafana template variables at the top:

1. **Data Source (`$datasource`)** — selects the Prometheus datasource.
2. **Omgeving / Cluster (`$cluster`)** — `label_values(kube_pod_info, cluster)` (`testing` or `production`).
3. **Namespace (`$namespace`)** — `label_values(kube_pod_info{cluster=~"$cluster"}, namespace)`.
4. **Pod (`$pod`)** — `label_values(kube_pod_info{cluster=~"$cluster", namespace=~"$namespace"}, pod)`.

Every pod CPU, RAM, throttling, network, disk, restart, and log panel filters on `{cluster=~"$cluster", namespace=~"$namespace", pod=~"$pod"}`, ensuring that selecting a single cluster, namespace, and pod isolates **only** that time series.

---

## 4. MiniPC Capacity, Retention & Resource Limits (`TC-164-03`)

### Underlying MiniPC VM Capacity (`Infra/Setup/terraform.tfvars`)

| Proxmox VM | vCPU | RAM | Disk | Role |
| :--- | :--- | :--- | :--- | :--- |
| `k8s-masterServer` | `2 vCPU` | `4096 MiB` (4 GiB) | `32 GB` | Kubernetes Control Plane |
| `k8s-workerServer` | **`8 vCPU`** | **`8192 MiB` (8 GiB)** | **`128 GB`** | All Essers + Monitoring workloads + Longhorn storage |
| `pipeline-runner` | `2 vCPU` | `2084 MiB` (~2 GiB) | `32 GB` | GitHub Actions Self-Hosted Runner |

### Concrete Monitoring Retention, Storage & Compute Budgets

| Component | Testing (`values-testing.yaml`) | Production (`values-production.yaml`) |
| :--- | :--- | :--- |
| **Prometheus Retention / Size Cap** | **`7d`** / **`8GiB`** | **`14d`** / **`12GiB`** |
| **Prometheus PVC (Longhorn)** | **`10Gi`** (`ReadWriteOnce`) | **`15Gi`** (`ReadWriteOnce`) |
| **Prometheus Scrape / Eval Interval** | `30s` / `30s` | `15s` / `15s` |
| **Prometheus CPU (req / limit)** | `150m` / `750m` | `250m` / `1000m` |
| **Prometheus RAM (req / limit)** | `512Mi` / `1280Mi` | `768Mi` / `1536Mi` |
| **Grafana PVC (Longhorn)** | `5Gi` (`ReadWriteOnce`) | `5Gi` (`ReadWriteOnce`) |
| **Grafana CPU (req / limit)** | `50m` / `300m` | `100m` / `400m` |
| **Grafana RAM (req / limit)** | `128Mi` / `384Mi` | `192Mi` / `512Mi` |
| **Grafana Sidecar CPU / RAM** | `10m / 100m`, `32Mi / 128Mi` | `10m / 100m`, `32Mi / 128Mi` |
| **Alertmanager Retention / PVC** | `120h` (5d) / `2Gi` | `168h` (7d) / `2Gi` |
| **Alertmanager CPU (req / limit)** | `25m` / `100m` | `25m` / `100m` |
| **Alertmanager RAM (req / limit)** | `64Mi` / `128Mi` | `64Mi` / `192Mi` |
| **kube-state-metrics CPU / RAM** | `25m / 100m`, `64Mi / 128Mi` | `50m / 150m`, `64Mi / 192Mi` |
| **Prometheus Operator CPU / RAM** | `50m / 200m`, `128Mi / 256Mi` | `50m / 200m`, `128Mi / 256Mi` |
| **Config Reloader CPU / RAM** | `10m / 100m`, `32Mi / 64Mi` | `10m / 100m`, `32Mi / 64Mi` |
| **Loki Retention / PVC (`loki-statefulset.yaml`)** | `168h` (7d) / `15Gi` | `168h` (7d) / `15Gi` |
| **Loki CPU / RAM** | `100m / 400m`, `192Mi / 512Mi` | `100m / 400m`, `192Mi / 512Mi` |
| **Alloy DaemonSet (per node) CPU / RAM** | `50m / 200m`, `64Mi / 256Mi` | `50m / 200m`, `64Mi / 256Mi` |
| **Total Monitoring Storage (PVC)** | **`32 GiB`** (+ 20 GiB SFTP = **52 GiB / 128 GB**) | **`37 GiB`** (+ 70 GiB SFTP = **107 GiB / 128 GB**) |
| **Total Monitoring CPU (req / limit)** | `~470m` req / `~2.15 cores` max limit (of 8 vCPU) | `~645m` req / `~2.65 cores` max limit (of 8 vCPU) |
| **Total Monitoring RAM (req / limit)** | `~1.09 GiB` req / `~3.06 GiB` max limit (of 8 GiB) | `~1.44 GiB` req / `~3.56 GiB` max limit (of 8 GiB) |

> **Upgrade note for existing Production PVCs:** Kubernetes does not allow shrinking an already-bound PVC in place. If the Production cluster previously provisioned larger `50Gi` Prometheus / `20Gi` Grafana / `5Gi` Alertmanager PVCs, delete and recreate those PVCs during a maintenance window before running `helm upgrade` with the tighter MiniPC sizes.

---

## 5. GitOps Dashboards (`Kubernetes/cluster-addons/monitoring/dashboards/`)

All three dashboards are auto-discovered by the Grafana sidecar (`grafana_dashboard: "1"`) into the **Essers** folder:

1. **Kubernetes Pod & Cluster Resource Health (`essers-k8s-cluster-overview`)**
   * Primary dashboard for **Issue 164** (`TC-164-01`, `TC-164-02`, `TC-164-03`).
   * Shows cluster saturation, Prometheus targets UP/DOWN, pod CPU & RAM vs requests/limits, CPU throttling, pod network RX/TX, pod disk I/O with Longhorn PVC & node disk fallbacks, MiniPC monitoring RAM/TSDB footprint, and Loki logs.
2. **Essers Mapping — Proposals & AI Pipeline (`essers-proposals-ai-pipeline`)**
   * Live proposal overview from `Mapping_Proposal` (`/metrics`): active proposals, `AI Generating (Bezig)`, `Ready for Review`, `In Review / AI Check`, `Returned`, **`Failed AI Proposals`**, **Shared SFTP status (UP/DOWN)**, and **Oldest Running AI Job age**.
   * Incoming upload queue depth (`pending`, `processing`, `failed`), upload outcomes, AI generation & AI review decisions (`Mapping_Converter` `/metrics`), Excel→JSON conversion counts, average AI processing duration, Ingress traffic/latency, and live logs filtered on `mapping-proposal` & `mapping-converter`.
3. **Essers Mapping End-to-End Zone Telemetry (`essers-services-overview`)**
   * Zone 1 (Preparation), Zone 2 (Shared Storage), and Zone 3 (Runtime) deployment availability, CPU/RAM, SFTP PVC fill %, pod network I/O, restarts, and application logs — with `cluster`, `namespace`, and `pod` filters.

---

## 6. Refined Discord Alerts (Alertmanager + `PrometheusRule`)

Alerting rules live in [`alerts/essers-alerts.yaml`](./alerts/essers-alerts.yaml) and are dispatched by Alertmanager to Discord using `${{ secrets.DISCORD_WEBHOOK_URL }}` (injected during `kubernetes-deploy.yml`):

* **Noise reduction:** Built-in `Watchdog` and `InfoInhibitor` alerts are routed to the `null` receiver; inhibition rules suppress duplicate warnings when a `critical` alert, `NodeNotReady`, or `ServiceZeroReplicasAvailable` is already firing.
* **Environment clarity & formatting:** Every Discord title starts with `🔴 [TESTING][CRITICAL]`, `🟠 [TESTING][WARNING]`, `🔴 [PRODUCTION][CRITICAL]`, `🟠 [PRODUCTION][WARNING]`, or `✅ [...][RESOLVED]`, renders clean multi-line Markdown (only showing populated labels), includes a concrete Dutch action hint (`Actie`), and links straight to the matching Grafana dashboard.
* **Alert groups:**
  * **Workloads:** `ServiceZeroReplicasAvailable`, `PodCrashLooping`, `PodOOMKilled`, `PodFrequentRestarts`, `PodStuckPending`, `ContainerNearMemoryLimit`, `ContainerHighCpuThrottling`.
  * **Proposals & AI Pipeline:** `MappingProposalSftpUnreachable`, `MappingProposalAiFailed`, `MappingProposalAiStuck` (> 15m), `MappingProposalUploadErrors`, `MappingConverterAiReviewErrors`.
  * **Storage, Nodes & Monitoring:** `PvcStorageSpaceWarning` (> 75%), `PvcStorageSpaceCritical` (> 85%), `NodeNotReady`, `NodeHighMemoryUsage` (> 85%), `NodeHighDiskUsage` (> 85%), `IngressHigh5xxErrorRate` (> 5% with > 0.05 req/s traffic guard), `PrometheusTargetDown`.

---

## 7. Deployment & Verification Commands

```bash
# Deploy kube-prometheus-stack (testing or production)
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  -f Kubernetes/cluster-addons/monitoring/values-testing.yaml

# Apply NetworkPolicies, ServiceMonitors, Alert Rules, Loki, Alloy, Datasources & Dashboards
kubectl apply -f Kubernetes/cluster-addons/monitoring/network-policies.yaml
kubectl apply -f Kubernetes/cluster-addons/monitoring/service-monitors/
kubectl apply -k Kubernetes/cluster-addons/monitoring/alerts/
kubectl apply -k Kubernetes/cluster-addons/monitoring/loki/
kubectl apply -k Kubernetes/cluster-addons/monitoring/alloy/
kubectl apply -k Kubernetes/cluster-addons/monitoring/datasources/
kubectl apply -k Kubernetes/cluster-addons/monitoring/dashboards/

# Verification checks (TC-164-01 / TC-164-03)
kubectl get pods,pvc,ingress,servicemonitor,prometheusrule -n monitoring
kubectl get prometheus kube-prometheus-stack-prometheus -n monitoring \
  -o jsonpath='{.spec.retention} / {.spec.retentionSize}{"\n"}'
```
