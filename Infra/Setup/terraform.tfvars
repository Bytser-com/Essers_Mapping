# ==============================================================================
# SECTION 1: PROXMOX PROVIDER CONFIGURATIONS (GLOBAL)
# ==============================================================================

# Explicitly specifying your non-sensitive target cluster mapping parameters.
download_datastore_id = "local"


# ==============================================================================
# SECTION 2: SHARED DEBIAN BASE CONFIGURATIONS (REUSABLE FOR ALL DEBIAN VMs)
# ==============================================================================

# These override or explicitly track the shared baseline configurations.
debian_cloud_image_file_name = "debian-13-genericcloud-amd64.qcow2"

debian_vm_efi_pre_enrolled_keys = true
debian_vm_startup_up_delay      = "30"
debian_vm_startup_down_delay    = "60"

debian_vm_username    = "sysadmin"
debian_vm_dns_servers = ["192.168.100.1", "1.1.1.1"]

debian_vm_timeout_create = "10m"
debian_vm_timeout_update = "10m"
debian_vm_timeout_delete = "5m"


# ==============================================================================
# SECTION 3: VM CONFIGURATIONS (INSTANCE-SPECIFIC)
# ==============================================================================


# ====================
# pipeline-runner
# ====================

pipeline-runner_vm_description = "Github Runner to run CI/CD pipelines in the network."
pipeline-runner_vm_tags        = ["CI/CD", "Linux", "Automated"]


# pipeline-runner
pipeline-runner_vm_name = "pipeline-runner"
pipeline-runner_vm_id   = 300

pipeline-runner_vm_started       = true
pipeline-runner_vm_on_boot       = true
pipeline-runner_vm_startup_order = "3"
pipeline-runner_vm_protection    = true # Protected against accidental destructions in Prod

pipeline-runner_vm_cpu_cores      = 2
pipeline-runner_vm_memory_size    = 2084
pipeline-runner_vm_disk_size_gb   = 32
pipeline-runner_vm_disk_backup    = true
pipeline-runner_vm_disk_replicate = true

pipeline-runner_vm_network_bridge   = "vmbr0"
pipeline-runner_vm_network_tag      = 0
pipeline-runner_vm_network_firewall = true
pipeline-runner_vm_network_mac      = null


# ====================
# k8s-master
# ====================

k8s-master_vm_description = "Kubernetes Control Plane to run container orchestrations."
k8s-master_vm_tags        = ["K8S", "Linux", "Automated"]


# k8s-master
k8s-master_vm_name = "k8s-masterServer"
k8s-master_vm_id   = 100

k8s-master_vm_started       = true
k8s-master_vm_on_boot       = true
k8s-master_vm_startup_order = "1"
k8s-master_vm_protection    = true # Protected against accidental destructions in Prod

k8s-master_vm_cpu_cores      = 2
k8s-master_vm_memory_size    = 4096
k8s-master_vm_disk_size_gb   = 32
k8s-master_vm_disk_backup    = true
k8s-master_vm_disk_replicate = true

k8s-master_vm_network_bridge   = "vmbr0"
k8s-master_vm_network_tag      = 0
k8s-master_vm_network_firewall = true
k8s-master_vm_network_mac      = null


# ====================
# k8s-worker
# ====================

k8s-worker_vm_description = "Kubernetes Worker Nodes to run container loads."
k8s-worker_vm_tags        = ["K8S", "Linux", "Automated"]


# k8s-worker
k8s-worker_vm_name = "k8s-workerServer"
k8s-worker_vm_id   = 200

k8s-worker_vm_started       = true
k8s-worker_vm_on_boot       = true
k8s-worker_vm_startup_order = "2"
k8s-worker_vm_protection    = true # Protected against accidental destructions in Prod

k8s-worker_vm_cpu_cores      = 8
k8s-worker_vm_memory_size    = 8192
k8s-worker_vm_disk_size_gb   = 128
k8s-worker_vm_disk_backup    = true
k8s-worker_vm_disk_replicate = true

k8s-worker_vm_network_bridge   = "vmbr0"
k8s-worker_vm_network_tag      = 0
k8s-worker_vm_network_firewall = true
k8s-worker_vm_network_mac      = null
