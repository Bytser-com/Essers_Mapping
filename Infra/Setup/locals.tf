locals {
  # Basic Instances
  basic_vms = {
    # pipeline-runner Hosts
    "pipeline-runner" = {
      name             = var.pipeline-runner_vm_name
      vm_id            = var.pipeline-runner_vm_id
      description      = var.pipeline-runner_vm_description
      node_name        = var.node01_name
      tags             = var.pipeline-runner_vm_tags
      protection       = var.pipeline-runner_vm_protection
      on_boot          = var.pipeline-runner_vm_on_boot
      startup_order    = var.pipeline-runner_vm_startup_order
      up_delay         = var.debian_vm_startup_up_delay
      down_delay       = var.debian_vm_startup_down_delay
      efi_datastore    = var.node01_name
      efi_pre_enroll   = var.debian_vm_efi_pre_enrolled_keys
      cpu_cores        = var.pipeline-runner_vm_cpu_cores
      memory_size      = var.pipeline-runner_vm_memory_size
      disk_datastore   = var.node01_name
      disk_size        = var.pipeline-runner_vm_disk_size_gb
      cloud_image      = proxmox_download_file.debian_cloud_image[var.node01_name].id
      disk_backup      = var.pipeline-runner_vm_disk_backup
      disk_replicate   = var.pipeline-runner_vm_disk_replicate
      network_bridge   = var.pipeline-runner_vm_network_bridge
      network_tag      = var.pipeline-runner_vm_network_tag
      network_firewall = var.pipeline-runner_vm_network_firewall
      network_mac      = var.pipeline-runner_vm_network_mac
      ipv4_address     = var.pipeline-runner_vm_ipv4_address
      ipv4_gateway     = var.ipv4_gateway
      dns_domain       = var.pipeline-runner_vm_dns_domain
      dns_servers      = var.debian_vm_dns_servers
      username         = var.debian_vm_username
      password         = var.debian_vm_user_password
      ssh_keys = [
      trimspace(var.pipeline_ssh_public_key)]
      init_datatore = var.node01_name
      vm_started    = var.pipeline-runner_vm_started
    }

    # k8s-master Hosts
    "k8s-master" = {
      name             = var.k8s-master_vm_name
      vm_id            = var.k8s-master_vm_id
      description      = var.k8s-master_vm_description
      node_name        = var.node01_name
      tags             = var.k8s-master_vm_tags
      protection       = var.k8s-master_vm_protection
      on_boot          = var.k8s-master_vm_on_boot
      startup_order    = var.k8s-master_vm_startup_order
      up_delay         = var.debian_vm_startup_up_delay
      down_delay       = var.debian_vm_startup_down_delay
      efi_datastore    = var.node01_name
      efi_pre_enroll   = var.debian_vm_efi_pre_enrolled_keys
      cpu_cores        = var.k8s-master_vm_cpu_cores
      memory_size      = var.k8s-master_vm_memory_size
      disk_datastore   = var.node01_name
      disk_size        = var.k8s-master_vm_disk_size_gb
      cloud_image      = proxmox_download_file.debian_cloud_image[var.node01_name].id
      disk_backup      = var.k8s-master_vm_disk_backup
      disk_replicate   = var.k8s-master_vm_disk_replicate
      network_bridge   = var.k8s-master_vm_network_bridge
      network_tag      = var.k8s-master_vm_network_tag
      network_firewall = var.k8s-master_vm_network_firewall
      network_mac      = var.k8s-master_vm_network_mac
      ipv4_address     = var.k8s-master_vm_ipv4_address
      ipv4_gateway     = var.ipv4_gateway
      dns_domain       = var.k8s-master_vm_dns_domain
      dns_servers      = var.debian_vm_dns_servers
      username         = var.debian_vm_username
      password         = var.debian_vm_user_password
      ssh_keys = [
      trimspace(var.pipeline_ssh_public_key)]
      init_datatore = var.node01_name
      vm_started    = var.k8s-master_vm_started
    }

    # k8s-worker Hosts
    "k8s-worker" = {
      name             = var.k8s-worker_vm_name
      vm_id            = var.k8s-worker_vm_id
      description      = var.k8s-worker_vm_description
      node_name        = var.node01_name
      tags             = var.k8s-worker_vm_tags
      protection       = var.k8s-worker_vm_protection
      on_boot          = var.k8s-worker_vm_on_boot
      startup_order    = var.k8s-worker_vm_startup_order
      up_delay         = var.debian_vm_startup_up_delay
      down_delay       = var.debian_vm_startup_down_delay
      efi_datastore    = var.node01_name
      efi_pre_enroll   = var.debian_vm_efi_pre_enrolled_keys
      cpu_cores        = var.k8s-worker_vm_cpu_cores
      memory_size      = var.k8s-worker_vm_memory_size
      disk_datastore   = var.node01_name
      disk_size        = var.k8s-worker_vm_disk_size_gb
      cloud_image      = proxmox_download_file.debian_cloud_image[var.node01_name].id
      disk_backup      = var.k8s-worker_vm_disk_backup
      disk_replicate   = var.k8s-worker_vm_disk_replicate
      network_bridge   = var.k8s-worker_vm_network_bridge
      network_tag      = var.k8s-worker_vm_network_tag
      network_firewall = var.k8s-worker_vm_network_firewall
      network_mac      = var.k8s-worker_vm_network_mac
      ipv4_address     = var.k8s-worker_vm_ipv4_address
      ipv4_gateway     = var.ipv4_gateway
      dns_domain       = var.k8s-worker_vm_dns_domain
      dns_servers      = var.debian_vm_dns_servers
      username         = var.debian_vm_username
      password         = var.debian_vm_user_password
      ssh_keys = [
      trimspace(var.pipeline_ssh_public_key)]
      init_datatore = var.node01_name
      vm_started    = var.k8s-worker_vm_started
    }
  }
}
