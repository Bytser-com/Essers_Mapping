locals {
  # Basic Instances
  basic_vms = {
    # pipeline_runner Hosts
    "pipeline_runner" = {
      name             = var.pipeline_runner_vm_name
      vm_id            = var.pipeline_runner_vm_id
      description      = var.pipeline_runner_vm_description
      node_name        = var.node01_name
      tags             = var.pipeline_runner_vm_tags
      protection       = var.pipeline_runner_vm_protection
      on_boot          = var.pipeline_runner_vm_on_boot
      startup_order    = var.pipeline_runner_vm_startup_order
      up_delay         = var.debian_vm_startup_up_delay
      down_delay       = var.debian_vm_startup_down_delay
      efi_datastore    = var.local_datastore_id
      efi_pre_enroll   = var.debian_vm_efi_pre_enrolled_keys
      cpu_cores        = var.pipeline_runner_vm_cpu_cores
      memory_size      = var.pipeline_runner_vm_memory_size
      disk_datastore   = var.local_datastore_id
      disk_size        = var.pipeline_runner_vm_disk_size_gb
      cloud_image      = proxmox_download_file.debian_cloud_image[var.node01_name].id
      disk_backup      = var.pipeline_runner_vm_disk_backup
      disk_replicate   = var.pipeline_runner_vm_disk_replicate
      network_bridge   = var.pipeline_runner_vm_network_bridge
      network_tag      = var.pipeline_runner_vm_network_tag
      network_firewall = var.pipeline_runner_vm_network_firewall
      network_mac      = var.pipeline_runner_vm_network_mac
      ipv4_address     = var.pipeline_runner_vm_ipv4_address
      ipv4_gateway     = var.ipv4_gateway
      dns_domain       = var.pipeline_runner_vm_dns_domain
      dns_servers      = var.debian_vm_dns_servers
      username         = var.debian_vm_username
      password         = var.debian_vm_user_password
      ssh_keys = [
      trimspace(var.pipeline_ssh_public_key)]
      init_datatore = var.local_datastore_id
      vm_started    = var.pipeline_runner_vm_started
    }

    # k8s_master Hosts
    "k8s_master" = {
      name             = var.k8s_master_vm_name
      vm_id            = var.k8s_master_vm_id
      description      = var.k8s_master_vm_description
      node_name        = var.node01_name
      tags             = var.k8s_master_vm_tags
      protection       = var.k8s_master_vm_protection
      on_boot          = var.k8s_master_vm_on_boot
      startup_order    = var.k8s_master_vm_startup_order
      up_delay         = var.debian_vm_startup_up_delay
      down_delay       = var.debian_vm_startup_down_delay
      efi_datastore    = var.local_datastore_id
      efi_pre_enroll   = var.debian_vm_efi_pre_enrolled_keys
      cpu_cores        = var.k8s_master_vm_cpu_cores
      memory_size      = var.k8s_master_vm_memory_size
      disk_datastore   = var.local_datastore_id
      disk_size        = var.k8s_master_vm_disk_size_gb
      cloud_image      = proxmox_download_file.debian_cloud_image[var.node01_name].id
      disk_backup      = var.k8s_master_vm_disk_backup
      disk_replicate   = var.k8s_master_vm_disk_replicate
      network_bridge   = var.k8s_master_vm_network_bridge
      network_tag      = var.k8s_master_vm_network_tag
      network_firewall = var.k8s_master_vm_network_firewall
      network_mac      = var.k8s_master_vm_network_mac
      ipv4_address     = var.k8s_master_vm_ipv4_address
      ipv4_gateway     = var.ipv4_gateway
      dns_domain       = var.k8s_master_vm_dns_domain
      dns_servers      = var.debian_vm_dns_servers
      username         = var.debian_vm_username
      password         = var.debian_vm_user_password
      ssh_keys = [
      trimspace(var.pipeline_ssh_public_key)]
      init_datatore = var.local_datastore_id
      vm_started    = var.k8s_master_vm_started
    }

    # k8s_worker Hosts
    "k8s_worker" = {
      name             = var.k8s_worker_vm_name
      vm_id            = var.k8s_worker_vm_id
      description      = var.k8s_worker_vm_description
      node_name        = var.node01_name
      tags             = var.k8s_worker_vm_tags
      protection       = var.k8s_worker_vm_protection
      on_boot          = var.k8s_worker_vm_on_boot
      startup_order    = var.k8s_worker_vm_startup_order
      up_delay         = var.debian_vm_startup_up_delay
      down_delay       = var.debian_vm_startup_down_delay
      efi_datastore    = var.local_datastore_id
      efi_pre_enroll   = var.debian_vm_efi_pre_enrolled_keys
      cpu_cores        = var.k8s_worker_vm_cpu_cores
      memory_size      = var.k8s_worker_vm_memory_size
      disk_datastore   = var.local_datastore_id
      disk_size        = var.k8s_worker_vm_disk_size_gb
      cloud_image      = proxmox_download_file.debian_cloud_image[var.node01_name].id
      disk_backup      = var.k8s_worker_vm_disk_backup
      disk_replicate   = var.k8s_worker_vm_disk_replicate
      network_bridge   = var.k8s_worker_vm_network_bridge
      network_tag      = var.k8s_worker_vm_network_tag
      network_firewall = var.k8s_worker_vm_network_firewall
      network_mac      = var.k8s_worker_vm_network_mac
      ipv4_address     = var.k8s_worker_vm_ipv4_address
      ipv4_gateway     = var.ipv4_gateway
      dns_domain       = var.k8s_worker_vm_dns_domain
      dns_servers      = var.debian_vm_dns_servers
      username         = var.debian_vm_username
      password         = var.debian_vm_user_password
      ssh_keys = [
      trimspace(var.pipeline_ssh_public_key)]
      init_datatore = var.local_datastore_id
      vm_started    = var.k8s_worker_vm_started
    }
  }
}
