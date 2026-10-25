# Kubernetes Architecture & Manifests (`Essers_Mapping/Kubernetes`)

Industry-grade, Kustomize-based Kubernetes declarative architecture for **Essers Mapping**, structured into three distinct logical zones (**Preparation Stage**, **Shared-Storage In-Between Zone**, and **Runtime Stage**) with dedicated public LoadBalancer IPs and Calico Zero-Trust network isolation.

---

## 1. Directory Structure (`base` + `overlays`)

```text
Kubernetes/
├── README.MD
├── cluster-addons/
│   └── longhorn/
│       └── values-single-worker.yaml             # Longhorn Helm values tuned for 1 Worker (8 vCPU / 8GB RAM / 128GB)
├── base/                                         # Shared base manifests across all environments
│   ├── kustomization.yaml                        # Root base Kustomize definition & ConfigMap generator
│   ├── common/
│   │   ├── kustomization.yaml
│   │   ├── namespace.yaml                        # Namespace (Pod Security Standards), ResourceQuota, LimitRange
│   │   ├── secrets.yaml                          # Separated SFTPGo Secrets (sftp-shared & sftp-runtime)
│   │   └── network-policies.yaml                 # Calico Zero-Trust NetworkPolicies (Ingress & Egress per zone)
│   ├── preparation/                              # ZONE 1: PREPARATION STAGE
│   │   ├── kustomization.yaml
│   │   ├── frontend.yaml                         # NGINX Frontend + /api/* Reverse Proxy (Public IP: .101 / .201)
│   │   ├── mapping-converter.yaml                # Python Backend 1 (Internal ClusterIP only)
│   │   ├── mapping-proposal.yaml                 # Python Backend 2 (Internal ClusterIP only)
│   │   └── version-control-backend.yaml          # Java Spring Boot Version Control Backend (Internal ClusterIP only)
│   ├── shared-storage/                           # ZONE 2: IN-BETWEEN SHARED STORAGE ZONE
│   │   ├── kustomization.yaml
│   │   └── sftp-shared.yaml                      # SFTPGo Shared Server + Longhorn RWX PVC (Public IP: .102 / .202)
│   └── runtime/                                  # ZONE 3: RUNTIME STAGE
│       ├── kustomization.yaml
│       ├── sftp-runtime.yaml                     # SFTPGo Runtime Server + Longhorn RWX PVC (Public IP: .103 / .203)
│       └── runtime-backend.yaml                  # Java Spring Boot Runtime Backend (Internal ClusterIP only)
└── overlays/
    ├── testing/                                  # Testing Environment (IPs: 192.168.100.101-103)
    │   ├── kustomization.yaml                    # Prep: 2 replicas (1+1 spare), Runtime: 3 replicas (2+1 spare)
    │   ├── hpa.yaml                              # Testing HPAs (Prep: 2..3, Runtime: 3..5)
    │   ├── metallb-ippool.yaml                   # MetalLB L2 Pool for 192.168.100.101 - 192.168.100.103
    │   └── patches/
    │       ├── loadbalancer-ips-patch.yaml       # Binds .101 (frontend), .102 (sftp-shared), .103 (sftp-runtime)
    │       └── resources-patch.yaml              # Testing CPU/RAM sizing, 10Gi Longhorn PVCs, nodeSelector: testing
    └── production/                               # Production Environment (IPs: 192.168.100.201-203)
        ├── kustomization.yaml                    # Prep & Runtime: 3 baseline replicas (2+1 hot spare)
        ├── hpa.yaml                              # Production HPAs (Prep: 3..4, Runtime: 3..5)
        ├── metallb-ippool.yaml                   # MetalLB L2 Pool for 192.168.100.201 - 192.168.100.203
        └── patches/
            ├── loadbalancer-ips-patch.yaml       # Binds .201 (frontend), .202 (sftp-shared), .203 (sftp-runtime)
            └── resources-patch.yaml              # Production CPU/RAM sizing, PDB minAvailable=2, 35Gi Longhorn PVCs
```

---

## 2. System Zones, IP Address Plan & Access Matrix

### Dedicated Public IP Plan (`LoadBalancer` Services)

| Public Service | Logical Zone | Open Ports | Testing IP | Production IP | Purpose |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **`frontend`** (NGINX) | `preparation` | `80`, `443` | **`192.168.100.101`** | **`192.168.100.201`** | Serves web UI & proxies `/api/converter/*`, `/api/proposal/*`, `/api/version-control/*` |
| **`sftp-shared`** (SFTPGo) | `shared-storage` (In-Between) | `22` (SFTP), `8080` (WebUI/API) | **`192.168.100.102`** | **`192.168.100.202`** | Shared SFTPGo file share (external SFTP clients + all internal workloads) |
| **`sftp-runtime`** (SFTPGo) | `runtime` | `22` (SFTP), `8080` (WebUI/API) | **`192.168.100.103`** | **`192.168.100.203`** | Runtime SFTPGo file share (external SFTP clients + `runtime-backend` ONLY) |

---

### Complete Workload, Replica Scaling (+1 Hot Spare) & Connectivity Matrix

| Workload | GHCR Container Image | Zone (`essers.io/zone`) | Service Type | Testing Replicas (`Min+Spare .. Max`) | Production Replicas (`Min+Spare .. Max`) | Publicly Reachable? | Reachable by `frontend`? | `sftp-shared` Access | `sftp-runtime` Access |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`frontend`** (NGINX) | `ghcr.io/bytser-com/essers_mapping/frontend` | `preparation` | `LoadBalancer` | **`2`** (`1+1` .. max `3`) | **`3`** (`2+1` .. max `4`) | **YES (`.101` / `.201`)** | — | **Read / Write** | **BLOCKED** |
| **`mapping-converter`** (Python) | `ghcr.io/bytser-com/essers_mapping/mapping-converter` | `preparation` | `ClusterIP` (`:8000`) | **`2`** (`1+1` .. max `3`) | **`3`** (`2+1` .. max `4`) | **NO** (`/api/converter/`) | **YES** | **Read / Write** | **BLOCKED** |
| **`mapping-proposal`** (Python) | `ghcr.io/bytser-com/essers_mapping/mapping-proposal` | `preparation` | `ClusterIP` (`:8000`) | **`2`** (`1+1` .. max `3`) | **`3`** (`2+1` .. max `4`) | **NO** (`/api/proposal/`) | **YES** | **Read / Write** | **BLOCKED** |
| **`version-control-backend`** (Java) | `ghcr.io/bytser-com/essers_mapping/version-control-backend` | `preparation` | `ClusterIP` (`:8080`) | **`2`** (`1+1` .. max `3`) | **`3`** (`2+1` .. max `4`) | **NO** (`/api/version-control/`) | **YES** | **Read / Write** | **BLOCKED** |
| **`sftp-shared`** (SFTPGo) | `drakkan/sftpgo:v2.6` | `shared-storage` | `LoadBalancer` (`:22, :8080`) | **`2`** (`1+1` .. max `3`) | **`3`** (`2+1` .. max `4`) | **YES (`.102` / `.202`)** | **YES** | — | — |
| **`runtime-backend`** (Java) | `ghcr.io/bytser-com/essers_mapping/runtime-backend` | `runtime` | `ClusterIP` (`:8080`) | **`3`** (`2+1` .. max `5`) | **`3`** (`2+1` .. max `5`) | **NO** | **BLOCKED** | **Read / Write** | **Read / Write (Exclusive)** |
| **`sftp-runtime`** (SFTPGo) | `drakkan/sftpgo:v2.6` | `runtime` | `LoadBalancer` (`:22, :8080`) | **`3`** (`2+1` .. max `5`) | **`3`** (`2+1` .. max `5`) | **YES (`.103` / `.203`)** | **BLOCKED** | — | — |

---

## 3. How Frontend Routing & Zone Isolation Work

### 1. NGINX Frontend Reverse Proxy (`base/preparation/frontend.yaml`)
The `frontend` Deployment includes a pre-configured `frontend-nginx-config` ConfigMap that:
- Serves your SPA static files on `/` (ports `80` and `443`).
- Proxies all `/api/*` calls internally over Kubernetes DNS so your backends stay completely private (`ClusterIP`):
  - `/api/converter/*` $\rightarrow$ `http://mapping-converter:8000/`
  - `/api/proposal/*` $\rightarrow$ `http://mapping-proposal:8000/`
  - `/api/version-control/*` $\rightarrow$ `http://version-control-backend:8080/`
- Has full Read/Write access to `sftp-shared` (both via SFTP at `sftp-shared:22` and mounted PVC at `/mnt/sftp-shared`).

### 2. Zero-Trust Network Policies (`base/common/network-policies.yaml`)
Enforced automatically by **Calico CNI**:
- **`allow-public-to-frontend`**: Opens TCP `80` and `443` on `frontend`.
- **`allow-frontend-to-preparation-backends`**: Ensures `mapping-converter`, `mapping-proposal`, and `version-control-backend` ONLY accept traffic from `frontend` (and fellow `preparation` backends)—never from outside or from the `runtime` zone.
- **`restrict-preparation-zone-egress`**: Strict Egress policy on the `preparation` zone so `frontend`, `mapping-converter`, `mapping-proposal`, and `version-control-backend` can ONLY talk to CoreDNS, each other, and `sftp-shared`—making it impossible for them to connect to `sftp-runtime` or `runtime-backend`.
- **`allow-all-authorized-and-public-to-sftp-shared`**: Allows external SFTP connections on `.102`/`.202` (port `22`) plus internal connections from all 5 workloads (`frontend`, `mapping-converter`, `mapping-proposal`, `version-control-backend`, and `runtime-backend`).
- **`allow-runtime-backend-and-public-to-sftp-runtime`**: Allows external SFTP connections on `.103`/`.203` (port `22`), while restricting internal cluster connections (`10.244.0.0/16`) exclusively to `runtime-backend`.

---

## 4. Standard Execution Commands (from Bastion / Runner VM)

### Step 1: Enable MetalLB (Once per Cluster for Dedicated LoadBalancer IPs)
Because you are running on Proxmox VMs (`kubeadm`), install **MetalLB** so Kubernetes assigns and advertises `192.168.100.101-103` (Testing) and `192.168.100.201-203` (Production) on your LAN:
```bash
# 1. Install MetalLB
kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.14.9/config/manifests/metallb-native.yaml
kubectl wait --namespace metallb-system --for=condition=ready pod --selector=app=metallb --timeout=120s

# 2. Apply the IP Address Pool for your target cluster:
# On Testing cluster (192.168.100.101 - 192.168.100.103):
kubectl apply -f Kubernetes/overlays/testing/metallb-ippool.yaml

# On Production cluster (192.168.100.201 - 192.168.100.203):
kubectl apply -f Kubernetes/overlays/production/metallb-ippool.yaml
```

### Step 2: Preview or Deploy Testing & Production Overlays
```bash
# Preview rendered manifests
kubectl kustomize Kubernetes/overlays/testing
kubectl kustomize Kubernetes/overlays/production

# Deploy Testing Environment (2 replicas per service, IPs: .101, .102, .103)
kubectl apply -k Kubernetes/overlays/testing

# Deploy Production Environment (5 replicas per service + HPA, IPs: .201, .202, .203)
kubectl apply -k Kubernetes/overlays/production
```

### Step 3: Verify Dedicated IPs & Pods
```bash
kubectl get svc,pods,pvc,netpol -n essers-mapping-testing -o wide
```
You will see:
- `service/frontend` $\rightarrow$ `EXTERNAL-IP: 192.168.100.101` (`80:.../TCP, 443:.../TCP`)
- `service/sftp-shared` $\rightarrow$ `EXTERNAL-IP: 192.168.100.102` (`22:.../TCP`)
- `service/sftp-runtime` $\rightarrow$ `EXTERNAL-IP: 192.168.100.103` (`22:.../TCP`)
- `service/mapping-converter`, `service/mapping-proposal`, `service/version-control-backend`, `service/runtime-backend` $\rightarrow$ `ClusterIP` (`EXTERNAL-IP: <none>`)

---

## 5. Permanent Storage Architecture (Longhorn `ReadWriteMany`) & Alternatives

### What We Use Right Now: Longhorn (`storageClassName: longhorn` + `ReadWriteMany`)
In [`base/shared-storage/sftp-shared.yaml`](./base/shared-storage/sftp-shared.yaml) and [`base/runtime/sftp-runtime.yaml`](./base/runtime/sftp-runtime.yaml), permanent storage is configured for **Longhorn** using `storageClassName: longhorn` and `accessModes: [ReadWriteMany]` (`10Gi` per share in Testing, `35Gi` per share in Production).

#### How to Install Longhorn on Your 1-Worker Cluster (`8 vCPU / 8GB RAM / 128GB Disk`)
1. **Install OS prerequisites on `k8s-workerServer`** (`open-iscsi` and `nfs-common` are required by Longhorn for block attachment and `ReadWriteMany` NFSv4 mounts):
   ```bash
   # On k8s-workerServer (or add 'open-iscsi' and 'nfs-common' to Infra/Config/roles/common/defaults/main.yml):
   sudo apt-get update && sudo apt-get install -y open-iscsi nfs-common
   sudo systemctl enable --now iscsid
   ```
2. **Install Longhorn via Helm (from your Bastion / Runner VM)** using our single-worker tuned values file [`cluster-addons/longhorn/values-single-worker.yaml`](./cluster-addons/longhorn/values-single-worker.yaml) (which sets `defaultReplicaCount: 1` and lowers CPU/RAM reservations):
   ```bash
   helm repo add longhorn https://charts.longhorn.io
   helm repo update
   helm upgrade --install longhorn longhorn/longhorn \
     --namespace longhorn-system \
     --create-namespace \
     -f Kubernetes/cluster-addons/longhorn/values-single-worker.yaml
   ```

#### Resource Budget Breakdown on Your Worker VM (`8 vCPU / 8 GB RAM / 128 GB Disk`)
We specifically tuned [`overlays/production/patches/resources-patch.yaml`](./overlays/production/patches/resources-patch.yaml) so that even **Production (25 app pods + 2 SFTP pods + Longhorn)** fits comfortably inside your single `8 vCPU / 8 GB RAM / 128 GB` worker VM:
- **CPU Requests**: `3.45 vCPU` requested by all 27 app/SFTP pods + `~0.6 vCPU` for Longhorn & system = **`~4.05 / 8.0 vCPU` (50% utilization)**.
- **RAM Requests**: `5.05 GB` requested by all 27 app/SFTP pods + `~0.9 GB` for Longhorn + `~1.0 GB` for OS/kubelet/Calico = **`~6.95 / 8.0 GB RAM` (~1 GB free buffer)**.
- **Disk Capacity**: `20 GB` (Debian OS + container images) + `70 GB` (`35Gi` `sftp-shared-pvc` + `35Gi` `sftp-runtime-pvc` with `defaultReplicaCount: 1`) = **`90 / 128 GB` (`38 GB` free buffer)**.

---

### Comparison of the 4 Main Storage Methods for Proxmox + `kubeadm`

| Storage Method | Access Modes | Multi-Worker Support? | Setup Complexity | Best For |
| :--- | :---: | :---: | :---: | :--- |
| **1. Rancher `local-path-provisioner`** | `ReadWriteOnce` | Tied to 1 Worker Node | Very Easy (1 command) | Single-worker clusters (like your current 1-master + 1-worker setup) |
| **2. NFS Subdir External Provisioner** | `ReadWriteOnce`, `ReadWriteMany` | **Yes** (All nodes share via NFS) | Easy | Multi-worker clusters needing shared filesystem mounts (`RWX`) |
| **3. Longhorn (Cloud-Native Distributed Storage)** | `ReadWriteOnce`, `ReadWriteMany` | **Yes** (Replicated across nodes) | Medium | Production HA clusters with 2–3+ worker nodes |
| **4. Proxmox CSI Plugin (`proxmox-csi-plugin`)** | `ReadWriteOnce` | Yes (attaches Proxmox disk to node) | Medium–High | Native Proxmox VM disk management per PVC |

---

#### Option 1: Rancher `local-path-provisioner` (Recommended for Your Current 1-Worker Setup)
Automatically creates directories on the Worker VM's disk (`/opt/local-path-provisioner/...`) whenever a PVC is requested.
- **Install (1 command)**:
  ```bash
  kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.30/deploy/local-path-storage.yaml
  kubectl patch storageclass local-path -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
  ```
- **Pros**:
  - Zero external dependencies; installs in 5 seconds.
  - Native disk speed (writes directly to your Proxmox Worker VM's VirtIO SCSI disk, which is already backed up by Proxmox).
  - Works out-of-the-box with our current manifests without changing a single line.
- **Cons**:
  - Data lives on `k8s-workerServer`'s local disk. If you later add a 2nd or 3rd worker node, pods mounting that PVC directly must either run on that same worker node or talk to the SFTP pod over the network (`sftp-shared:22` / `sftp-runtime:22`) rather than mounting `/mnt/sftp-*` locally.

#### Option 2: NFS External Provisioner (`nfs-subdir-external-provisioner`)
Uses an NFS share (hosted on your Proxmox host, a NAS, or your Bastion/SFTP VM) to dynamically create subdirectories per PVC.
- **Pros**:
  - Supports true **`ReadWriteMany` (`RWX`)** across unlimited worker nodes.
  - Centralizes all files in one place outside the K8s worker node, making backups and inspection very easy.
- **Cons**:
  - Requires an NFS server to be running on your network.
  - Slightly higher latency than local block storage due to network filesystem overhead.

#### Option 3: Longhorn (CNCF Distributed Block Storage + Built-in NFS `RWX`)
Turns your worker nodes' disks into a replicated distributed storage cluster with a web UI, snapshots, and S3/NFS backups.
- **Pros**:
  - Industry standard for bare-metal/on-prem Kubernetes.
  - Supports both `ReadWriteOnce` and `ReadWriteMany` (via built-in NFSv4 server), plus automated volume snapshots and disaster recovery.
- **Cons**:
  - Heavier resource footprint (~1–2 CPU cores and ~2 GB RAM overhead across the cluster).
  - Really shines when you have **at least 2 or 3 worker nodes** for replication; overkill for a single worker node.

#### Option 4: Proxmox CSI Plugin (`sergelogvinov/proxmox-csi-plugin`)
Connects Kubernetes directly to the Proxmox VE API so every PVC creates a real virtual disk (`vm-XXX-disk-Y`) on your Proxmox datastore (`local-lvm` / `ceph` / `zfs`) and hot-plugs it into the Worker VM.
- **Pros**:
  - Clean separation: application data lives on dedicated Proxmox virtual disks rather than inside the Worker OS root disk.
  - Proxmox can snapshot/backup individual PVC disks directly.
- **Cons**:
  - Requires configuring Proxmox API tokens inside Kubernetes Secrets.
  - Only supports `ReadWriteOnce` (block disk can only be attached to one Worker VM at a time), unless paired with an SFTP/NFS server pod.

