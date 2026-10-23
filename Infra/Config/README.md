# Infrastructure Configuration (Ansible)

Industry-grade, role-based Ansible architecture for configuring the Debian 13 (Trixie) virtual machines provisioned via Terraform in [`Infra/Setup`](../Setup/main.tf).

## 1. Architecture & Role Overview

| Role | Target Group | Responsibilities |
| :--- | :--- | :--- |
| **`common`** | `all` | Preflight validation, APT safe upgrade, base packages, Proxmox `qemu-guest-agent` & `fstrim.timer`, `/etc/hosts` cluster mapping, `systemd-timesyncd` NTP, passwordless `sudo`, SSH hardening, Fail2Ban, and `unattended-upgrades`. |
| **`containerd`** | `k8s_cluster` | Disables active swap & `/etc/fstab` swap entries, loads `overlay` and `br_netfilter` kernel modules, configures Kubernetes CRI `sysctl` network parameters, and installs/configures `containerd` (`SystemdCgroup = true`). |
| **`k8s_common`** | `k8s_cluster` | Configures official Kubernetes APT repository (`pkgs.k8s.io`), installs and version-pins (`dpkg hold`) `kubelet`, `kubeadm`, and `kubectl`, and configures `--node-ip` and `/etc/crictl.yaml`. |
| **`k8s_master`** | `k8s_masters` | Idempotent `kubeadm init` using declarative `kubeadm-config.yaml`, distributes `~/.kube/config`, deploys Calico/Flannel CNI, installs Helm 3, and generates a dynamic worker join command. |
| **`k8s_worker`** | `k8s_workers` | Idempotently joins worker nodes to the Kubernetes Control Plane (`creates: /etc/kubernetes/kubelet.conf`), waits for node readiness, and applies worker role & environment labels. |
| **`github_runner`** | `runners` | Creates `ghrunner` service user, creates `/opt/terraform-state/essers-infra-setup/{production,testing}` directories, installs CI/CD CLI stack (Terraform, Ansible, `kubectl`, Helm, Docker), and downloads/registers the GitHub Actions self-hosted runner systemd service. |

---

## 2. Standard Execution Workflow

```bash
cd Infra/Config

# 1. Install required Ansible Galaxy collections
ansible-galaxy collection install -r requirements.yml

# 2. Load required environment variables (fails fast if IPs/domains are missing)
source .env

# 3. Validate syntax
ansible-playbook -i inventories/testing/hosts.yml site.yml --syntax-check

# 4. Run full configuration (Testing)
ansible-playbook -i inventories/testing/hosts.yml site.yml

# 5. Run full configuration (Production)
ansible-playbook -i inventories/production/hosts.yml site.yml
```

### Running Specific Stages or Tags

```bash
# Run only OS bootstrap & security hardening
ansible-playbook -i inventories/testing/hosts.yml playbooks/bootstrap.yml

# Run only Kubernetes cluster configuration
ansible-playbook -i inventories/testing/hosts.yml playbooks/kubernetes.yml

# Run only CI/CD GitHub Runner setup
ansible-playbook -i inventories/testing/hosts.yml playbooks/runner.yml

# Run specific tagged tasks (e.g., security or cni)
ansible-playbook -i inventories/testing/hosts.yml site.yml --tags "security"
```
