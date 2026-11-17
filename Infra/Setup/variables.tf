# ==============================================================================
# SECTION 1: PROXMOX PROVIDER CONFIGURATIONS (GLOBAL)
# ==============================================================================

variable "proxmox_api_url" {
  type        = string
  description = "The HTTPS API endpoint URL for your Proxmox VE host cluster."
}

variable "proxmox_api_insecure" {
  type        = bool
  default     = true
  description = "Set to true to bypass SSL/TLS certificate verification for self_signed certificates."
}

variable "proxmox_api_token" {
  type        = string
  sensitive   = true
  description = "The Proxmox API token string (USER@REALM!TOKENID=UUID) used to authenticate provider operations."
}

variable "proxmox_api_username" {
  type        = string
  default     = "root@pam"
  description = "The Proxmox standard web console login username (Alternative to API Token auth)."
}

variable "proxmox_api_password" {
  type        = string
  sensitive   = true
  default     = ""
  description = "The Proxmox standard web console login password (Alternative to API Token auth)."
}

variable "proxmox_ssh_password" {
  type        = string
  sensitive   = true
  default     = ""
  description = "The system password for the Proxmox host root/user account if an SSH Agent isn't used."
}

variable "proxmox_ssh_private_key" {
  type        = string
  sensitive   = true
  default     = ""
  description = "The raw private SSH key used to authenticate with the Proxmox host."
}

variable "node01_name" {
  type        = string
  description = "The targeted Proxmox node where assets are downloaded and VMs are run."
}

variable "local_datastore_id" {
  type        = string
  default     = "local"
  description = "The identity of the storage pool where downloaded image files are stored."
}

variable "pipeline_ssh_public_key" {
  type        = string
  description = "The public SSH key string assigned to task runners, automation pipelines, or Ansible controllers."
}


# ==============================================================================
# SECTION 2: SHARED DEBIAN BASE CONFIGURATIONS (REUSABLE FOR ALL DEBIAN VMs)
# ==============================================================================

variable "debian_cloud_image_file_name" {
  type        = string
  description = "The targeted filename given to the imported disk image inside Proxmox storage."
}

variable "debian_cloud_image_url" {
  type        = string
  description = "The source URL pointing to the official Debian distribution cloud_init image file."
}

variable "debian_cloud_image_checksum" {
  type        = string
  description = "The secure hash verification signature corresponding to the cloud image file."
}

variable "debian_vm_efi_pre_enrolled_keys" {
  type        = bool
  default     = true
  description = "Ensures UEFI firmware paths utilize pre_loaded Secure Boot standard keys."
}

variable "debian_vm_startup_up_delay" {
  type        = string
  default     = "60"
  description = "Shared delay time (in seconds) before moving on to the next VM in the boot sequence."
}

variable "debian_vm_startup_down_delay" {
  type        = string
  default     = "60"
  description = "Shared buffer window (in seconds) allowed before forcefully stopping a VM on cluster shutdown."
}

variable "debian_vm_user_password" {
  type        = string
  sensitive   = true
  description = "The cryptographically secure password text or hash assigned to the initialized admin account."
}

variable "debian_vm_username" {
  type        = string
  default     = "sysadmin"
  description = "The default administrator username created on the Debian virtual machine for SSH access."
}

variable "debian_vm_dns_servers" {
  type        = list(string)
  default     = ["1.1.1.1", "1.1.0.0"]
  description = "The list of DNS servers to be used by the Debian VM."
}

variable "ipv4_gateway" {
  type        = string
  description = "The upstream hardware router gateway IPv4 address routing local traffic out."
}

variable "debian_vm_timeout_create" {
  type        = string
  default     = "30m"
  description = "The baseline allocation window allowed for the cluster to finalize machine creation steps."
}

variable "debian_vm_timeout_update" {
  type        = string
  default     = "30m"
  description = "The total adjustment timeout timeframe allowed before marking hardware changes as timed out."
}

variable "debian_vm_timeout_delete" {
  type        = string
  default     = "10m"
  description = "The timeline permitted for cleanup routines to purge storage instances safely during teardown."
}


# ==============================================================================
# SECTION 4: VM CONFIGURATIONS (INSTANCE_SPECIFIC)
# ==============================================================================


# ====================
# pipeline_runner
# ====================

variable "pipeline_runner_vm_description" {
  type        = string
  description = "The descriptive text notes visible within the Proxmox web interface for this specific VM."
}

variable "pipeline_runner_vm_tags" {
  type        = list(string)
  default     = ["Dev"]
  description = "An array of environmental labels or tags used to organize this specific instance."
}


# pipeline_runner
variable "pipeline_runner_vm_name" {
  type        = string
  description = "The unique system name / hostname assigned to the target virtual machine."
}

variable "pipeline_runner_vm_id" {
  type        = number
  description = "The explicit numeric virtual machine ID (VMID) within the Proxmox cluster."
}

variable "pipeline_runner_vm_started" {
  type        = bool
  default     = false
  description = "Configures the running state of this instance Virtual Machine."
}

variable "pipeline_runner_vm_on_boot" {
  type        = bool
  default     = false
  description = "Configures this instance to boot automatically when the Proxmox host initializes."
}

variable "pipeline_runner_vm_startup_order" {
  type        = string
  default     = "9999"
  description = "The exact startup hierarchy boot ranking priority for this specific VM."
}

variable "pipeline_runner_vm_protection" {
  type        = bool
  default     = false
  description = "Locks this virtual instance in place inside Proxmox to prevent accidental destruction."
}

variable "pipeline_runner_vm_cpu_cores" {
  type        = number
  default     = 6
  description = "The total number of physical vCPU cores allocated to this machine profile."
}

variable "pipeline_runner_vm_memory_size" {
  type        = number
  default     = 8192
  description = "The total amount of system RAM allocated to this guest OS in Megabytes (MiB)."
}

variable "pipeline_runner_vm_disk_size_gb" {
  type        = number
  default     = 64
  description = "The volume size of the primary OS root storage block expressed in Gigabytes (GB)."
}

variable "pipeline_runner_vm_disk_backup" {
  type        = bool
  default     = true
  description = "Whether this instance's root storage disk is included in global backup schedules."
}

variable "pipeline_runner_vm_disk_replicate" {
  type        = bool
  default     = true
  description = "Whether this instance's root storage disk is included in global replication schedules."
}

variable "pipeline_runner_vm_network_bridge" {
  type        = string
  default     = "vmbr0"
  description = "The virtual network switch bridge name allocated for this machine's network interface."
}

variable "pipeline_runner_vm_network_tag" {
  type        = number
  description = "The internal network VLAN ID partition tag used to restrict this machine's communication boundaries."
}

variable "pipeline_runner_vm_network_firewall" {
  type        = bool
  default     = true
  description = "Enables the baseline Proxmox hypervisor firewall filter context on this adapter interface."
}

variable "pipeline_runner_vm_network_mac" {
  type        = string
  default     = null
  description = "A custom hardware MAC address for the network interface on the host (set to null to auto_generate)."
}

variable "pipeline_runner_vm_ipv4_address" {
  type        = string
  description = "The static IPv4 allocation config along with CIDR subnet prefix notation (e.g., 10.145.0.230/24)."
}

variable "pipeline_runner_vm_dns_domain" {
  type        = string
  description = "The DNS domain name assigned to this virtual machine for hostname resolution."
}


# ====================
# k8s_master
# ====================

variable "k8s_master_vm_description" {
  type        = string
  description = "The descriptive text notes visible within the Proxmox web interface for this specific VM."
}

variable "k8s_master_vm_tags" {
  type        = list(string)
  default     = ["Dev"]
  description = "An array of environmental labels or tags used to organize this specific instance."
}


# k8s_master
variable "k8s_master_vm_name" {
  type        = string
  description = "The unique system name / hostname assigned to the target virtual machine."
}

variable "k8s_master_vm_id" {
  type        = number
  description = "The explicit numeric virtual machine ID (VMID) within the Proxmox cluster."
}

variable "k8s_master_vm_started" {
  type        = bool
  default     = false
  description = "Configures the running state of this instance Virtual Machine."
}

variable "k8s_master_vm_on_boot" {
  type        = bool
  default     = false
  description = "Configures this instance to boot automatically when the Proxmox host initializes."
}

variable "k8s_master_vm_startup_order" {
  type        = string
  default     = "9999"
  description = "The exact startup hierarchy boot ranking priority for this specific VM."
}

variable "k8s_master_vm_protection" {
  type        = bool
  default     = false
  description = "Locks this virtual instance in place inside Proxmox to prevent accidental destruction."
}

variable "k8s_master_vm_cpu_cores" {
  type        = number
  default     = 6
  description = "The total number of physical vCPU cores allocated to this machine profile."
}

variable "k8s_master_vm_memory_size" {
  type        = number
  default     = 8192
  description = "The total amount of system RAM allocated to this guest OS in Megabytes (MiB)."
}

variable "k8s_master_vm_disk_size_gb" {
  type        = number
  default     = 64
  description = "The volume size of the primary OS root storage block expressed in Gigabytes (GB)."
}

variable "k8s_master_vm_disk_backup" {
  type        = bool
  default     = true
  description = "Whether this instance's root storage disk is included in global backup schedules."
}

variable "k8s_master_vm_disk_replicate" {
  type        = bool
  default     = true
  description = "Whether this instance's root storage disk is included in global replication schedules."
}

variable "k8s_master_vm_network_bridge" {
  type        = string
  default     = "vmbr0"
  description = "The virtual network switch bridge name allocated for this machine's network interface."
}

variable "k8s_master_vm_network_tag" {
  type        = number
  description = "The internal network VLAN ID partition tag used to restrict this machine's communication boundaries."
}

variable "k8s_master_vm_network_firewall" {
  type        = bool
  default     = true
  description = "Enables the baseline Proxmox hypervisor firewall filter context on this adapter interface."
}

variable "k8s_master_vm_network_mac" {
  type        = string
  default     = null
  description = "A custom hardware MAC address for the network interface on the host (set to null to auto_generate)."
}

variable "k8s_master_vm_ipv4_address" {
  type        = string
  description = "The static IPv4 allocation config along with CIDR subnet prefix notation (e.g., 10.145.0.230/24)."
}

variable "k8s_master_vm_dns_domain" {
  type        = string
  description = "The DNS domain name assigned to this virtual machine for hostname resolution."
}


# ====================
# k8s_worker
# ====================

variable "k8s_worker_vm_description" {
  type        = string
  description = "The descriptive text notes visible within the Proxmox web interface for this specific VM."
}

variable "k8s_worker_vm_tags" {
  type        = list(string)
  default     = ["Dev"]
  description = "An array of environmental labels or tags used to organize this specific instance."
}


# k8s_worker
variable "k8s_worker_vm_name" {
  type        = string
  description = "The unique system name / hostname assigned to the target virtual machine."
}

variable "k8s_worker_vm_id" {
  type        = number
  description = "The explicit numeric virtual machine ID (VMID) within the Proxmox cluster."
}

variable "k8s_worker_vm_started" {
  type        = bool
  default     = false
  description = "Configures the running state of this instance Virtual Machine."
}

variable "k8s_worker_vm_on_boot" {
  type        = bool
  default     = false
  description = "Configures this instance to boot automatically when the Proxmox host initializes."
}

variable "k8s_worker_vm_startup_order" {
  type        = string
  default     = "9999"
  description = "The exact startup hierarchy boot ranking priority for this specific VM."
}

variable "k8s_worker_vm_protection" {
  type        = bool
  default     = false
  description = "Locks this virtual instance in place inside Proxmox to prevent accidental destruction."
}

variable "k8s_worker_vm_cpu_cores" {
  type        = number
  default     = 6
  description = "The total number of physical vCPU cores allocated to this machine profile."
}

variable "k8s_worker_vm_memory_size" {
  type        = number
  default     = 8192
  description = "The total amount of system RAM allocated to this guest OS in Megabytes (MiB)."
}

variable "k8s_worker_vm_disk_size_gb" {
  type        = number
  default     = 64
  description = "The volume size of the primary OS root storage block expressed in Gigabytes (GB)."
}

variable "k8s_worker_vm_disk_backup" {
  type        = bool
  default     = true
  description = "Whether this instance's root storage disk is included in global backup schedules."
}

variable "k8s_worker_vm_disk_replicate" {
  type        = bool
  default     = true
  description = "Whether this instance's root storage disk is included in global replication schedules."
}

variable "k8s_worker_vm_network_bridge" {
  type        = string
  default     = "vmbr0"
  description = "The virtual network switch bridge name allocated for this machine's network interface."
}

variable "k8s_worker_vm_network_tag" {
  type        = number
  description = "The internal network VLAN ID partition tag used to restrict this machine's communication boundaries."
}

variable "k8s_worker_vm_network_firewall" {
  type        = bool
  default     = true
  description = "Enables the baseline Proxmox hypervisor firewall filter context on this adapter interface."
}

variable "k8s_worker_vm_network_mac" {
  type        = string
  default     = null
  description = "A custom hardware MAC address for the network interface on the host (set to null to auto_generate)."
}

variable "k8s_worker_vm_ipv4_address" {
  type        = string
  description = "The static IPv4 allocation config along with CIDR subnet prefix notation (e.g., 10.145.0.230/24)."
}

variable "k8s_worker_vm_dns_domain" {
  type        = string
  description = "The DNS domain name assigned to this virtual machine for hostname resolution."
}
