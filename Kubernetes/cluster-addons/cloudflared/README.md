# Cloudflare Tunnel (`cloudflared`) Add-on

Secure outbound-only reverse proxy connecting your Kubernetes clusters to Cloudflare's global edge network without opening any firewall ports, configuring NAT, or requiring a static public IP.

---

## Architecture Overview (Separate Testing & Production Clusters)

Since Testing and Production are separate Kubernetes clusters running on their own dedicated servers/VMs:

```text
Visitor (Internet)
      │
      ├─────────────────────────────────────────────────┐
      ▼  HTTPS (443)                                    ▼  HTTPS (443)
https://testing-essers.shystack.com          https://production-essers.shystack.com
      │                                                 │
      ▼                                                 ▼
Cloudflare Edge Network                           Cloudflare Edge Network
(Tunnel: essers-k8s-testing)                      (Tunnel: essers-k8s-production)
      │                                                 │
      ▲  Outbound Tunnel 1                              ▲  Outbound Tunnel 2
cloudflared Pod (Testing Cluster)                 cloudflared Pod (Production Cluster)
      │                                                 │
      ▼  Internal HTTP (80)                             ▼  Internal HTTP (80)
NGINX Ingress (Testing Cluster)                   NGINX Ingress (Production Cluster)
      │                                                 │
      ▼  Internal HTTP (8080)                           ▼  Internal HTTP (8080)
Testing Frontend Pod                              Production Frontend Pod
(`essers-mapping-testing`)                        (`essers-mapping-production`)
```

### Why Separate Tunnels per Cluster?
Because each cluster runs on its own virtual machines with its own internal network:
1. **Testing Tunnel (`essers-k8s-testing`)**: Connects only to the Testing cluster and routes `testing-essers.shystack.com`.
2. **Production Tunnel (`essers-k8s-production`)**: Connects only to the Production cluster and routes `production-essers.shystack.com`.
3. **Environment Isolation**: If the testing cluster is rebuilt, modified, or destroyed, the production cluster and its tunnel remain 100% untouched and operational.

---

## Step 1: Create the Two Tunnels in Cloudflare Zero Trust

Log in to [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/) and go to **Networks** → **Tunnels**.

### Tunnel 1: Testing Cluster
1. Click **Create a tunnel**.
2. Name: `essers-k8s-testing` → Click **Save tunnel**.
3. Select **Docker** environment and copy the tunnel token (string after `--token`).
4. In the **Public Hostname** tab:
   - Click **Add a public hostname**.
   - **Subdomain**: `testing-essers`
   - **Domain**: `shystack.com`
   - **Service**:
     - **Type**: `HTTP`
     - **URL**: `ingress-nginx-controller.ingress-nginx.svc.cluster.local:80`
   - Under **Additional application settings** → **HTTP Settings**:
     - **HTTP Host Header**: `testing-essers.shystack.com`
   - Click **Save hostname**.

### Tunnel 2: Production Cluster
1. Click **Create a tunnel**.
2. Name: `essers-k8s-production` → Click **Save tunnel**.
3. Select **Docker** environment and copy the tunnel token (string after `--token`).
4. In the **Public Hostname** tab:
   - Click **Add a public hostname**.
   - **Subdomain**: `production-essers`
   - **Domain**: `shystack.com`
   - **Service**:
     - **Type**: `HTTP`
     - **URL**: `ingress-nginx-controller.ingress-nginx.svc.cluster.local:80`
   - Under **Additional application settings** → **HTTP Settings**:
     - **HTTP Host Header**: `production-essers.shystack.com`
   - Click **Save hostname**.

---

## Step 2: Configure GitHub Actions Secrets

In your GitHub repository, navigate to **Settings** → **Environments**:

1. Open Environment **`Testing`**:
   - Add secret `CLOUDFLARE_TUNNEL_TOKEN` with the token from **Tunnel 1 (`essers-k8s-testing`)**.
2. Open Environment **`Production`**:
   - Add secret `CLOUDFLARE_TUNNEL_TOKEN` with the token from **Tunnel 2 (`essers-k8s-production`)**.

---

## Step 3: Automated Deployment via GitHub Actions Pipeline

When you run [infra-pipeline.yml](../../.github/workflows/infra-pipeline.yml) or push to branch `Testing` or `main`:
1. Terraform provisions the VMs for that environment.
2. Ansible configures the OS, containerd, and bootstraps the k8s cluster.
3. Kubernetes deploy:
   - MetalLB, Longhorn, cert-manager, and Ingress NGINX are configured.
   - The pipeline automatically extracts the environment-specific `CLOUDFLARE_TUNNEL_TOKEN`.
   - Creates the `cloudflare` namespace and `cloudflared-token` Secret.
   - Deploys 1 `cloudflared` pod into that cluster.
   - Verifies the tunnel is healthy (`kubectl rollout status deployment/cloudflared -n cloudflare`).
   - Deploys the application workloads.

---

## Manual Deployment (Local Testing / Troubleshooting)

To manually deploy or test on either cluster:

```bash
# 1. Create the namespace
kubectl apply -f Kubernetes/cluster-addons/cloudflared/namespace.yaml

# 2. Store the cluster's specific tunnel token
kubectl create secret generic cloudflared-token \
  --namespace cloudflare \
  --from-literal=token="<YOUR_COPIED_TUNNEL_TOKEN_FOR_THIS_CLUSTER>"

# 3. Deploy the cloudflared pod
kubectl apply -k Kubernetes/cluster-addons/cloudflared/

# 4. Verify pod status
kubectl get pods -n cloudflare
kubectl logs -n cloudflare -l app=cloudflared --tail=20
```
