# 1. Install required Ansible Galaxy collections (once)
    ansible-galaxy collection install -r requirements.yml
  
    # 2. Load your environment variables from .env
    source .env
  
    # 3. Run EVERYTHING (Bootstrap + K8s Master/Worker + GitHub Runner VM)
    # For Testing:
    ansible-playbook -i inventories/testing/hosts.yml site.yml --tags all,runner
  
    # For Production:
    ansible-playbook -i inventories/production/hosts.yml site.yml --tags all,runner


### Other Useful Tag Combinations

  • Ping all hosts trough ansible:
    ansible -i inventories/testing/hosts.yml all -m ping
  
  • Dry-run / syntax check everything first:
    ansible-playbook -i inventories/testing/hosts.yml site.yml --tags all,runner --syntax-check
  
  • Run ONLY the never-tagged Runner plays (OS bootstrap + github_runner role):
    ansible-playbook -i inventories/testing/hosts.yml site.yml --tags runner
  
  • Run default plays ONLY (K8s cluster, skipping never-tagged runner plays):
    ansible-playbook -i inventories/testing/hosts.yml site.yml













# Infrastructure Configuration (Ansible)

Industry-grade, role-based Ansible architecture for configuring the Debian 13 (Trixie) virtual machines provisioned via Terraform in [`Infra/Setup`](../Setup/main.tf).

## 1. Architecture & Role Overview

| Role | Target Group | Responsibilities |
| :--- | :--- | :--- |
| **`common`** | `k8s_cluster` (default) / `runners` (`never` tag) | Preflight validation, APT safe upgrade, base packages, Proxmox `qemu-guest-agent` & `fstrim.timer`, `/etc/hosts` cluster mapping, `systemd-timesyncd` NTP, passwordless `sudo`, SSH hardening, Fail2Ban, and `unattended-upgrades`. |
| **`containerd`** | `k8s_cluster` | Disables active swap & `/etc/fstab` swap entries, loads `overlay` and `br_netfilter` kernel modules, configures Kubernetes CRI `sysctl` network parameters, and installs/configures `containerd` (`SystemdCgroup = true`). |
| **`k8s_common`** | `k8s_cluster` | Configures official Kubernetes APT repository (`pkgs.k8s.io`), installs and version-pins (`dpkg hold`) `kubelet`, `kubeadm`, and `kubectl`, and configures `--node-ip` and `/etc/crictl.yaml`. |
| **`k8s_master`** | `k8s_masters` | Idempotent `kubeadm init` using declarative `kubeadm-config.yaml`, distributes `~/.kube/config`, deploys Calico/Flannel CNI, installs Helm 3, and generates a dynamic worker join command. |
| **`k8s_worker`** | `k8s_workers` | Idempotently joins worker nodes to the Kubernetes Control Plane (`creates: /etc/kubernetes/kubelet.conf`), waits for node readiness, and applies worker role & environment labels. |
| **`github_runner`** | `runners` (`never` tag) | Creates `ghrunner` service user, creates `/opt/terraform-state/essers-infra-setup/{production,testing}` directories, installs CI/CD CLI stack (Terraform, Ansible, `kubectl`, Helm, Docker), fetches `/etc/kubernetes/admin.conf` from the Control Plane to configure `~/.kube/config` on the runner VM, and downloads/registers the GitHub Actions self-hosted runner systemd service. |

---

## 2. Standard Execution Workflow

```bash
cd Infra/Config

# 1. Install required Ansible Galaxy collections
ansible-galaxy collection install -r requirements.yml

# 2. Copy .env.example to .env, fill in values, and load environment variables
cp .env.example .env
source .env

# 3. Validate syntax
ansible-playbook -i inventories/testing/hosts.yml site.yml --syntax-check

# 4. Run default configuration (K8s cluster only; runner VM is skipped via 'never' tag)
ansible-playbook -i inventories/testing/hosts.yml site.yml

# 5. Run default configuration (Production)
ansible-playbook -i inventories/production/hosts.yml site.yml
```

### Running Specific Stages or the Runner VM (`never` Tag)

Because the `pipeline-runner` VM plays are tagged with `never`, they are skipped during normal runs unless explicitly requested via `--tags`:

```bash
# Run ONLY the CI/CD GitHub Runner setup (including OS bootstrap + github_runner role + kubeconfig)
ansible-playbook -i inventories/testing/hosts.yml site.yml --tags runner

# Run ONLY the github_runner role playbook directly on the runner VM
ansible-playbook -i inventories/testing/hosts.yml playbooks/runner.yml --tags runner

# Run ONLY the kubectl kubeconfig setup on the runner VM
ansible-playbook -i inventories/testing/hosts.yml playbooks/runner.yml --tags runner_kubeconfig

# Run EVERYTHING (Kubernetes cluster + CI/CD Runner VM) in a single run
ansible-playbook -i inventories/testing/hosts.yml site.yml --tags all,runner

# Run only OS bootstrap & security hardening (K8s nodes)
ansible-playbook -i inventories/testing/hosts.yml playbooks/bootstrap.yml

# Run only Kubernetes cluster configuration
ansible-playbook -i inventories/testing/hosts.yml playbooks/kubernetes.yml
```
