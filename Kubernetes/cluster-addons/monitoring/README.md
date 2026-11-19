# Kubernetes Monitoring & Grafana Dashboard Architecture

Declarative, enterprise-grade observability architecture for **Essers Mapping**, implementing end-to-end monitoring across all Kubernetes clusters using **Prometheus Operator (`kube-prometheus-stack`)**, **Grafana**, **Alertmanager**, and **Calico Zero-Trust NetworkPolicies**.

---

## 1. Architecture Overview

```text
                                        [ MetalLB Ingress ]
                         Testing: 192.168.100.101 | Production: 192.168.100.201
                                                 │
                                                 ▼
                                     ┌───────────────────────┐
                                     │  NGINX Ingress (443)  │ (cert-manager TLS)
                                     └───────────┬───────────┘
                                                 │
                                                 ▼
               ┌───────────────────────────────────────────────────────────────────┐
               │                         MONITORING NAMESPACE                      │
               │                                                                   │
               │  ┌─────────────────┐       Scrapes       ┌─────────────────────┐  │
               │  │     Grafana     │ ──────────────────► │  Prometheus Engine  │  │
               │  │   (Port 3000)   │                     │     (Port 9090)     │  │
               │  └────────┬────────┘                     └──────────┬──────────┘  │
               │           │ Auto-discovers                          │ Scrapes     │
               │           ▼                                         │             │
               │  ┌─────────────────┐                                │             │
               │  │ Dashboard C檐   │                                │             │
               │  │ (GitOps CMs)    │                                │             │
               │  └─────────────────┘                                │             │
               └─────────────────────────────────────────────────────┼─────────────┘
                                                                     │
            ┌────────────────────────────────┬───────────────────────┼──────────────────────────────┐
            │ (Ports 9100 / 10250)           │ (Port 8080)           │ (Ports 8000 / 8080)          │ (Ports 22 / 8080)
            ▼                                ▼                       ▼                              ▼
┌────────────────────────┐      ┌─────────────────────────┐  ┌─────────────────────────┐   ┌────────────────────────┐
│  Node Exporter & Kube  │      │   Ingress Controller    │  │  Essers Microservices   │   │  SFTPGo File Storage   │
│  (CPU, RAM, Disk, I/O) │      │  (req/s, 4xx/5xx, p95)  │  │  (JVM, Python, Probes)  │   │  (Shared & Runtime)    │
└────────────────────────┘      └─────────────────────────┘  └─────────────────────────┘   └────────────────────────┘
```

---

## 2. Environment Comparison (Testing vs Production)

| Feature / Metric | Testing Environment (`values-testing.yaml`) | Production Environment (`values-production.yaml`) |
| :--- | :--- | :--- |
| **Ingress LoadBalancer IP** | **`192.168.100.101`** (via testing Ingress) | **`192.168.100.201`** (via production Ingress) |
| **Ingress Hostname** | `grafana.testing.essers.local` / `grafana-test.example.com` | `grafana.essers.example.com` |
| **TLS Certificate Issuer** | `letsencrypt-staging` or `selfsigned-cluster-issuer` | `letsencrypt-prod` (Automated cert-manager renewal) |
| **Grafana Replicas** | `1` | `1` (with PodDisruptionBudget `minAvailable: 1`) |
| **Grafana PVC Storage** | `5Gi` (`storageClassName: longhorn`, `ReadWriteOnce`) | `20Gi` (`storageClassName: longhorn`, `ReadWriteOnce`) |
| **Prometheus Retention** | **7 Days** (`8Gi` maximum cap) | **30 Days** (`45Gi` maximum cap) |
| **Prometheus PVC Storage**| `10Gi` (`storageClassName: longhorn`, `ReadWriteOnce`) | `50Gi` (`storageClassName: longhorn`, `ReadWriteOnce`) |
| **Prometheus Sizing** | CPU: `150m` req / `800m` limit; RAM: `512Mi` req / `1.5Gi` limit | CPU: `500m` req / `1.5Core` limit; RAM: `2Gi` req / `4Gi` limit |
| **Scrape Interval** | `30s` | `15s` |
| **Admin Secret Source** | Configured in values file | Dedicated Kubernetes Secret (`grafana-admin-credentials`) |
| **GitOps Dashboard Sidecar** | Auto-discovers any ConfigMap with `grafana_dashboard: "1"` | Auto-discovers any ConfigMap with `grafana_dashboard: "1"` |

---

## 3. Directory Layout

```text
Kubernetes/cluster-addons/monitoring/
├── README.md                                 # Complete architecture & deployment guide
├── values-testing.yaml                       # Helm values tuned for Testing cluster (IP .101, 7d retention)
├── values-production.yaml                    # Helm values tuned for Production cluster (IP .201, 30d retention)
├── network-policies.yaml                     # Calico Zero-Trust NetworkPolicies for monitoring namespace
├── service-monitors/
│   ├── essers-mapping-servicemonitor.yaml    # Scrapes frontend, python backends, java backends, & SFTPGo
│   └── ingress-nginx-servicemonitor.yaml     # Scrapes NGINX Ingress Controller traffic & latency metrics
├── loki/
│   ├── kustomization.yaml                    # Kustomize manifest for Grafana Loki
│   ├── loki-config.yaml                      # Single-binary filesystem storage configuration
│   ├── loki-service.yaml                     # ClusterIP service on port 3100
│   └── loki-statefulset.yaml                 # StatefulSet with Longhorn PVC persistent log storage
├── alloy/
│   ├── kustomization.yaml                    # Kustomize manifest for Alloy DaemonSet
│   ├── alloy-rbac.yaml                       # ServiceAccount & ClusterRole for Kubernetes discovery
│   ├── alloy-config.yaml                     # River configuration for container log scraping
│   └── alloy-daemonset.yaml                  # DaemonSet tailing /var/log/pods across worker nodes
├── datasources/
│   ├── kustomization.yaml                    # Kustomize manifest for datasources
│   └── loki-datasource-cm.yaml               # Auto-provisioned Loki datasource for Grafana
└── dashboards/
    ├── kustomization.yaml                    # Kustomize manifest to apply dashboards
    ├── k8s-cluster-overview-cm.yaml          # All-in-one Kubernetes cluster, metrics, and logs dashboard
    └── essers-services-overview-cm.yaml      # Essers multi-zone microservices, telemetry, and app logs
```

---

## 4. Step-by-Step Installation

### Prerequisites
1. **MetalLB** installed with IP Address Pool applied (`testing`: `.101-.103`, `production`: `.201-.203`).
2. **cert-manager** and ClusterIssuers installed (`cluster-addons/cert-manager/cluster-issuers.yaml`).
3. **ingress-nginx** controller installed (`cluster-addons/ingress-nginx/values-{testing,production}.yaml`).
4. **Longhorn** storage installed (`cluster-addons/longhorn/values-single-worker.yaml`).

### Step A: Deploy on Testing Environment

```bash
# 1. Add Prometheus Community Helm Repository
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# 2. Deploy kube-prometheus-stack for Testing
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  -f Kubernetes/cluster-addons/monitoring/values-testing.yaml

# 3. Apply Calico Zero-Trust NetworkPolicies for monitoring
kubectl apply -f Kubernetes/cluster-addons/monitoring/network-policies.yaml

# 4. Apply ServiceMonitors for automated metric discovery
kubectl apply -f Kubernetes/cluster-addons/monitoring/service-monitors/

# 5. Deploy Loki Log Engine & Alloy Container Log Collector DaemonSet
kubectl apply -k Kubernetes/cluster-addons/monitoring/loki/
kubectl apply -k Kubernetes/cluster-addons/monitoring/alloy/
kubectl apply -k Kubernetes/cluster-addons/monitoring/datasources/

# 6. Deploy GitOps Dashboards
kubectl apply -k Kubernetes/cluster-addons/monitoring/dashboards/
```

### Step B: Deploy on Production Environment

```bash
# 1. Create monitoring namespace
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

# 2. Provision secure Grafana admin credentials secret
kubectl create secret generic grafana-admin-credentials \
  --namespace monitoring \
  --from-literal=admin-user=admin \
  --from-literal=admin-password="REPLACE_WITH_STRONG_PRODUCTION_SECRET" \
  --dry-run=client -o yaml | kubectl apply -f -

# 3. Deploy kube-prometheus-stack for Production
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  -f Kubernetes/cluster-addons/monitoring/values-production.yaml

# 4. Apply Calico Zero-Trust NetworkPolicies for monitoring
kubectl apply -f Kubernetes/cluster-addons/monitoring/network-policies.yaml

# 5. Apply ServiceMonitors for automated metric discovery
kubectl apply -f Kubernetes/cluster-addons/monitoring/service-monitors/

# 6. Deploy Loki Log Engine & Alloy Container Log Collector DaemonSet
kubectl apply -k Kubernetes/cluster-addons/monitoring/loki/
kubectl apply -k Kubernetes/cluster-addons/monitoring/alloy/
kubectl apply -k Kubernetes/cluster-addons/monitoring/datasources/

# 7. Deploy GitOps Dashboards
kubectl apply -k Kubernetes/cluster-addons/monitoring/dashboards/
```

---

## 5. Included Out-of-the-Box Dashboards

Both dashboards are loaded automatically via Grafana's sidecar container into the **"Essers Mapping"** folder:

### 1. Kubernetes Cluster & Workload Health (`essers-k8s-cluster-overview`)
Monitors the entire cluster and infrastructure foundation:
- **Cluster Saturation**: CPU (%) & RAM (%) gauges with dynamic warning (70%) and critical (85%) thresholds.
- **Node Infrastructure**: Ready nodes count, node CPU usage, memory allocatable vs working set, network I/O (bytes/sec), disk write throughput.
- **Pod & Container Health**: Running vs Pending pods, pod restart counter (1h) detecting CrashLoopBackOff.
- **Essers Workload Sizing**: Container CPU usage and memory working set per pod across all namespaces.
- **Deployment Status**: Desired vs Available replica count table.
- **Longhorn PVC Storage**: Volume capacity, used bytes, and percentage full.
- **Edge Ingress Telemetry**: Total HTTP request rate, status code distribution (2xx, 3xx, 4xx, 5xx), and p95/p99 request latency.

### 2. Essers Mapping End-to-End Zone Telemetry (`essers-services-overview`)
Monitors the microservices across all 3 architectural zones:
- **Zone 1 (Preparation Stage)**:
  - Pod health and replica counts for `frontend`, `mapping-converter`, `mapping-proposal`, and `version-control-backend`.
  - CPU and RAM footprint for preparation microservices.
- **Zone 2 (Shared Storage In-Between Zone)**:
  - `sftp-shared` replica availability, volume usage on Longhorn PVC, and network bandwidth.
- **Zone 3 (Runtime Stage)**:
  - `runtime-backend` and `sftp-runtime` pod availability and dedicated volume usage.
- **Application Runtime Engines**:
  - **Spring Boot JVM Telemetry**: Heap used vs max, GC pause times, and live threads.
  - **Python Backends**: Process memory and CPU consumption.

---

## 6. How to Export & Import Dashboards and Alerts (GitOps Workflow)

No manual imports in Grafana UI are needed on testing or production clusters! Everything is managed as code:

### A. Exporting & Importing Dashboards

1. **Design or Tweak in Grafana**:
   In your testing/local Grafana, create or edit panels.
2. **Export the Dashboard JSON**:
   Click **Dashboard Settings (Gear icon) $\rightarrow$ JSON Model $\rightarrow$ Copy to Clipboard** (or **Share $\rightarrow$ Export $\rightarrow$ Save to file**).
3. **Import via the Helper Script**:
   Save your file as `my-dashboard.json` and run:
   ```bash
   python3 Scripts/import-grafana-dashboard.py my-dashboard.json --name "Order Processing"
   ```
   This automatically wraps the JSON into a GitOps ConfigMap with `grafana_dashboard: "1"` under `Kubernetes/cluster-addons/monitoring/dashboards/` and registers it in `kustomization.yaml`.
4. **Commit & Push**:
   ```bash
   git add Kubernetes/cluster-addons/monitoring/dashboards/
   git commit -m "feat(monitoring): add order processing dashboard"
   git push origin Feature/<your-feature>
   ```
   Your **GitHub Actions pipeline** or **Ansible playbook** automatically applies the changes. Grafana's sidecar discovers the new dashboard within 5 seconds with **zero downtime or manual steps**!

---

### B. Defining & Importing Prometheus Alerts (`PrometheusRule`)

All alerting rules are declarative Kubernetes objects managed under [`Kubernetes/cluster-addons/monitoring/alerts/`](./alerts/):

1. **Add an Alert Definition**:
   Create or edit a rule in `Kubernetes/cluster-addons/monitoring/alerts/essers-alerts.yaml`:
   ```yaml
   apiVersion: monitoring.coreos.com/v1
   kind: PrometheusRule
   metadata:
     name: my-custom-alerts
     namespace: monitoring
     labels:
       role: alert-rules
       release: kube-prometheus-stack
   spec:
     groups:
       - name: custom-alerts
         rules:
           - alert: MyServiceHighLatency
             expr: histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) > 2
             for: 5m
             labels:
               severity: warning
             annotations:
               summary: "Service p95 latency exceeds 2 seconds"
   ```
2. **Commit & Deploy**:
   Once pushed, the CI/CD pipeline and Ansible automatically apply the alert rules, and Prometheus Operator immediately begins evaluating them. Alerts trigger notifications via Alertmanager.

---

## 7. Verification & Access

### Verify Pods & Ingress
```bash
kubectl get pods -n monitoring
kubectl get ingress -n monitoring
kubectl get pvc -n monitoring
```

### Accessing the Grafana UI
1. **Via Browser with DNS / Hosts file**:
   - Testing: `https://grafana.testing.essers.local` (or map host to `192.168.100.101` in `/etc/hosts`)
   - Production: `https://grafana.essers.example.com` (or map host to `192.168.100.201`)
2. **Via Port-Forward (Bypass Ingress during setup)**:
   ```bash
   kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80
   ```
   Open `http://localhost:3000` in your browser.
