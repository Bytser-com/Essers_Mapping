# Disaster Recovery Guide (DR) — Essers Mapping Platform

> **Target Audience:** DevOps Engineers, Platform Administrators, and Developers.  
> **Purpose:** Step-by-step procedures to recover, rebuild, and restore any layer of the Essers Mapping platform from total loss or failure.

---

## 1. Quick Reference Architecture & Inventory

### Virtual Machines (Proxmox VE Cluster)
| VM ID | Name | Role | IPv4 Address | OS / Image | Protection |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`100`** | `k8s-masterServer` | Kubernetes Control Plane (kubeadm + CNI) | `192.168.100.240/24` | Debian 13 (Trixie) Cloud-Init | `false` |
| **`200`** | `k8s-workerServer` | Kubernetes Worker Node (workloads + Longhorn) | `192.168.100.241/24` | Debian 13 (Trixie) Cloud-Init | `false` |
| **`300`** | `pipeline-runner` | GitHub Actions Self-Hosted Runner & Bastion | `192.168.100.242/24` | Debian 13 (Trixie) Cloud-Init | `false` |

* **Proxmox VE API (Testing)**: `https://192.168.100.3:8006/api2/json` (Node: `ProxVE-testing`)
* **Proxmox VE API (Production)**: `https://192.168.0.10:8006/api2/json` (Node: `ProxVE-production`)
* **Default Network Gateway**: `192.168.100.1` (DNS: `192.168.100.1`, `1.1.1.1`, `1.0.0.1`)

---

### Ingress & LoadBalancer IP Allocations (MetalLB)
| Service | Environment | External / MetalLB IP | Ports | Hostname / URL |
| :--- | :--- | :--- | :--- | :--- |
| **NGINX Ingress** | Testing | `192.168.100.101` | `80`, `443` | `https://testing-essers.shystack.com` |
| **Grafana Monitoring**| Testing | `192.168.100.101` | `443` | `https://monitor-testing.shystack.com` |
| **`sftp-shared`** | Testing | `192.168.100.102` | `22` (SFTP), `8080` (Web) | `http://192.168.100.102:8080/web/client` |
| **`sftp-runtime`**| Testing | `192.168.100.103` | `22` (SFTP), `8080` (Web) | `http://192.168.100.103:8080/web/client` |
| **NGINX Ingress** | Production| `192.168.100.201` | `80`, `443` | `https://production-essers.shystack.com` |
| **`sftp-shared`** | Production| `192.168.100.202` | `22` (SFTP), `8080` (Web) | `http://192.168.100.202:8080/web/client` |
| **`sftp-runtime`**| Production| `192.168.100.203` | `22` (SFTP), `8080` (Web) | `http://192.168.100.203:8080/web/client` |

---

## 2. Disaster Scenario A: Loss of Self-Hosted Runner VM (`pipeline-runner`)

### Problem
If VM `300` (`pipeline-runner`) is accidentally destroyed, corrupted, or unreachable, GitHub Actions cannot run any `self-hosted` CI/CD jobs. Workflows will hang in `Queued` waiting for a runner.

### Recovery Procedure: Bootstrap from Workstation / Laptop
You can bootstrap the official runner VM using a temporary runner running on any laptop or workstation on the local network (or connected via VPN).

#### Step 1: Ensure Workstation Prerequisites
Your workstation must:
1. Be connected to the same LAN / VPN as Proxmox (must be able to reach `192.168.100.3:8006` and ping `192.168.100.1`).
2. Have `curl`, `tar`, and `python3` installed.
3. Have `terraform` and `ansible` installed (if running Linux or WSL2).

#### Step 2: Download and Register a Temporary Runner
1. In GitHub, navigate to:  
   **Repository Settings $\rightarrow$ Actions $\rightarrow$ Runners $\rightarrow$ New runner $\rightarrow$ Linux (x64)**.
2. Open a terminal on your laptop and run:
   ```bash
   mkdir -p ~/temp-github-runner && cd ~/temp-github-runner
   curl -o actions-runner-linux-x64.tar.gz -L https://github.com/actions/runner/releases/download/v2.322.0/actions-runner-linux-x64-2.322.0.tar.gz
   tar xzf actions-runner-linux-x64.tar.gz
   ```
3. Configure the runner with the exact labels for the target environment:
   * **For Testing**:
     ```bash
     ./config.sh --url https://github.com/Bytser-com/Essers_Mapping \
       --token <TOKEN_FROM_GITHUB_UI> \
       --name "temp-laptop-runner" \
       --labels "self-hosted,linux,testing" \
       --unattended
     ```
   * **For Production**:
     ```bash
     ./config.sh --url https://github.com/Bytser-com/Essers_Mapping \
       --token <TOKEN_FROM_GITHUB_UI> \
       --name "temp-laptop-runner" \
       --labels "self-hosted,linux,production" \
       --unattended
     ```
4. Start the runner in the foreground:
   ```bash
   ./run.sh
   ```
   *(You will see: `Listening for Jobs`).*

#### Step 3: Trigger the Bootstrap Pipeline
1. Go to GitHub Actions: **Testing Infrastructure & Cluster Pipeline** (`infra-pipeline.yml`).
2. Click **Run workflow**:
   * **Branch**: `Testing` (or `main`)
   * **Deployment Scope**: Select **`runner-only`**
   * Click **Run workflow**.

#### What the pipeline does:
* **Stage 1 (Terraform)**: Connects to Proxmox and provisions VM `300` (`pipeline-runner`) from the Debian cloud image with IP `192.168.100.242`.
* **Stage 2 (Ansible)**: Executes `--tags runner --limit pipeline-runner`. It installs base hardening, Docker, Node Exporter, Grafana Alloy, and registers the **official** GitHub Runner service inside VM `300`.
* **Stage 3 (Kubernetes)**: Skipped automatically.

#### Step 4: Decommission the Temporary Runner
1. Once the job succeeds, check GitHub: **Settings $\rightarrow$ Actions $\rightarrow$ Runners**. You will see `pipeline-runner-testing` (or production) is now **Idle / Online**.
2. Stop the temporary runner on your laptop with `Ctrl + C`.
3. Cleanly remove it so no ghost runner remains:
   ```bash
   ./config.sh remove --token <TOKEN_FROM_GITHUB_UI>
   ```

---

## 3. Disaster Scenario B: Complete Kubernetes Cluster Loss

### Problem
Both `k8s-masterServer` (VM 100) and `k8s-workerServer` (VM 200) are corrupted, unresponsive, or deleted.

### Recovery Procedure
The infrastructure pipeline can rebuild the complete Kubernetes cluster and redeploy all applications in **under 15 minutes**.

#### Step 1: Clean Up Stale VMs (if they still exist)
* **Option 1 (via GitHub Actions Master Pipeline)**:
  Run **Testing Infrastructure & Cluster Pipeline** (`infra-pipeline.yml`) with:
  * **Terraform action**: `destroy`
  *(This automatically tears down VM 100 and VM 200, skips Ansible and Kubernetes stages, and safely leaves `pipeline-runner` online).*
* **Option 2 (via Proxmox UI)**:
  In Proxmox (`https://192.168.100.3:8006`):
  Right-click `100 (k8s-masterServer)` $\rightarrow$ Stop $\rightarrow$ Destroy.
  Right-click `200 (k8s-workerServer)` $\rightarrow$ Stop $\rightarrow$ Destroy.

#### Step 2: Trigger Full Infrastructure Rebuild
1. Go to GitHub Actions $\rightarrow$ **Testing Infrastructure & Cluster Pipeline**.
2. Click **Run workflow**:
   * **Branch**: `Testing`
   * **Deployment Scope**: `all`
   * **Terraform action**: `apply`
   * **Ansible mode**: `apply`
   * **Kubernetes mode**: `apply`
3. Click **Run workflow**.

#### Step 3: Verify Automated Deployment Sequence
* **Stage 1 (Terraform, ~1m)**: Provisions new Debian 13 VMs 100 and 200.
* **Stage 2 (Ansible, ~5m)**:
  * Bootstraps OS, firewall, timesync, and hostnames.
  * Initializes control plane with `kubeadm` and installs Calico CNI.
  * Joins worker node and labels it `node-role.kubernetes.io/worker=worker`.
  * Installs Node Exporter and Grafana Alloy telemetry on all VMs.
* **Stage 3 (Kubernetes Deploy, ~7m)**:
  * Deploys Longhorn storage engine.
  * Deploys Ingress NGINX controller and Cert-Manager.
  * Deploys Cloudflare edge tunnel (`cloudflared`).
  * Deploys Prometheus Operator, Grafana, and Loki.
  * Deploys applications: `mapping-proposal`, `mapping-converter`, `version-control-backend`, `frontend`, and SFTP storage.

---

## 4. Disaster Scenario C: SFTP Storage Access & Proposal Reseeding

### SFTP Credentials Reference
| Environment | Role | Target Interface | Username | Password Secret Key |
| :--- | :--- | :--- | :--- | :--- |
| **Testing** | Admin | `http://192.168.100.102:8080/web/admin` | `admin` | `Happy-ShaWebFTP*` |
| **Testing** | Client | `http://192.168.100.102:8080/web/client` | `shareduser` | `Happy-ShaSerFTP*` |
| **Testing** | SFTP | `sftp://192.168.100.102:22` | `shareduser` | `Happy-ShaSerFTP*` |
| **Production** | Admin | `http://192.168.100.202:8080/web/admin` | `admin` | `Essers-ShaWebFTP*` |
| **Production** | Client | `http://192.168.100.202:8080/web/client` | `shareduser` | `Essers-ShaSerFTP*` |
| **Production** | SFTP | `sftp://192.168.100.202:22` | `shareduser` | `Essers-ShaSerFTP*` |

### Triggering Proposal Seeding in Testing
If the shared SFTP volume was wiped or recreated, trigger sample proposal seeding:
* **Via Public Ingress**:
  ```bash
  curl -X POST "https://testing-essers.shystack.com/api/proposal/seed?force=true"
  ```
* **Via `kubectl` inside cluster**:
  ```bash
  kubectl exec -n testing $(kubectl get pod -n testing -l app=mapping-proposal -o jsonpath='{.items[0].metadata.name}') -- \
    python -m scripts.dev_seed --force
  ```

---

## 5. Disaster Scenario D: Monitoring (Grafana) Password Lockout

### Problem
Grafana admin password is forgotten or does not match the secret (because Grafana ignores secret updates once its SQLite database on the persistent volume is initialized).

### Recovery Procedure: Force-Reset Admin Password
Run the following `kubectl` command to reset the live admin password immediately without restarting or losing dashboards:

```bash
kubectl exec -n monitoring $(kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}') -c grafana -- \
  grafana-cli admin reset-admin-password 'HappyEssers*'
```

You can now log in at `https://monitor-testing.shystack.com/login` with `admin` / `HappyEssers*`.

---

## 6. Disaster Scenario E: Service Rollback

### Problem
A faulty code commit or deployment broke a running microservice in Testing or Production.

### Procedure 1: Rollback via Kubernetes CLI
```bash
# Roll back to the previous revision:
kubectl rollout undo deployment/frontend -n testing
kubectl rollout undo deployment/mapping-proposal -n testing
kubectl rollout undo deployment/version-control-backend -n testing

# Check rollback status:
kubectl rollout status deployment/frontend -n testing
```

### Procedure 2: Re-deploy Known Good Image
Each microservice repository workflow preserves image digests. Check the GitHub Package Registry (`ghcr.io/bytser-com/essers_mapping/<service>`) for the previous SHA tag and deploy via the **Service CD Pipeline** (`service-cd.yml`).

---

## 7. Disaster Recovery Checklist

When recovering from an outage, verify every layer sequentially:

- [ ] **Hypervisor Layer**: All 3 VMs (100, 200, 300) are running in Proxmox (`qm list`).
- [ ] **Runner Layer**: `pipeline-runner` is Idle / Online in GitHub Actions Settings.
- [ ] **Kubernetes Layer**: Both nodes report `Ready`:
  ```bash
  kubectl get nodes -o wide
  ```
- [ ] **Storage Layer**: Longhorn volume claims are `Bound`:
  ```bash
  kubectl get pvc -A
  ```
- [ ] **Network Layer**: MetalLB LoadBalancer services have acquired IPs (`.101`, `.102`, `.103`):
  ```bash
  kubectl get svc -A | grep LoadBalancer
  ```
- [ ] **Application Layer**: All deployment pods are `Running` (1/1 or 2/2):
  ```bash
  kubectl get pods -n testing
  ```
- [ ] **Ingress Layer**: Web and API endpoints return HTTP 200:
  ```bash
  curl -I https://testing-essers.shystack.com
  curl -I https://testing-essers.shystack.com/health
  curl -I https://monitor-testing.shystack.com
  ```
