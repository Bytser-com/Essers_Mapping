# Debian Official Cloud Image Download (Loop over all nodes)
resource "proxmox_download_file" "debian_cloud_image" {
  for_each            = toset([var.node01_name])
  content_type        = "import"
  datastore_id        = var.local_datastore_id
  file_name           = var.debian_cloud_image_file_name
  node_name           = each.value
  url                 = var.debian_cloud_image_url
  checksum            = var.debian_cloud_image_checksum
  checksum_algorithm  = "sha512"
  overwrite           = true
  overwrite_unmanaged = true
  upload_timeout      = 1200
}





# Basic Instances
resource "proxmox_virtual_environment_vm" "basic_vm" {
  # Loop trough all specified vm's
  for_each = local.basic_vms

  # VM Properties and specifications
  name        = each.value.name
  vm_id       = each.value.vm_id
  description = each.value.description
  node_name   = each.value.node_name
  tags        = each.value.tags
  protection  = each.value.protection # If set to true, Terraform can't delete the VM either. Some other operations are also blocked

  # Machine Type and boot settings
  machine         = "q35"
  scsi_hardware   = "virtio-scsi-single"
  boot_order      = ["scsi0"]
  hotplug         = "network,disk,usb"
  keyboard_layout = "en-us"
  on_boot         = each.value.on_boot # Corresponds to "Start at boot: Yes"
  startup {
    order      = each.value.startup_order
    up_delay   = each.value.up_delay   # Delay (in seconds) before moving on to the next VM
    down_delay = each.value.down_delay # Delay (in seconds) before forcefully stopping the VM
  }
  vga {
    type = "virtio"
  }

  # Operating System Type
  operating_system {
    type = "l26"
  }

  # Detailed SMBIOS Settings
  smbios {
    manufacturer = "Bytser"
    product      = "Virtual Machine"
    family       = "Proxmox Virtual Environment"
    serial       = each.value.name
  }

  # UEFI & EFI Disk Settings
  bios = "ovmf"
  efi_disk {
    datastore_id      = each.value.efi_datastore
    file_format       = "raw"
    type              = "4m"
    pre_enrolled_keys = each.value.efi_pre_enroll
  }

  # QEMU Guest Agent & Options
  agent {
    enabled = true
    trim    = true # Matches 'fstrim_cloned_disks: Enabled'
    type    = "virtio"
    timeout = "15m"
    wait_for_ip {
      disabled = true
    }
  }

  # CPU Configuration
  cpu {
    cores   = each.value.cpu_cores
    sockets = 1
    type    = "x86-64-v2-AES"
  }

  # Memory Configuration
  memory {
    dedicated = each.value.memory_size
  }

  # Disk Configuration (Repeated Block Style)
  disk {
    interface    = "scsi0"
    datastore_id = each.value.disk_datastore
    size         = each.value.disk_size

    import_from = proxmox_download_file.debian_cloud_image[each.value.node_name].id
    file_format = "raw"
    cache       = "none"
    aio         = "io_uring"
    discard     = "on"
    iothread    = true
    ssd         = true
    backup      = each.value.disk_backup
    replicate   = each.value.disk_replicate
  }

  # Network Device Configuration (Repeated Block Style)
  network_device {
    bridge      = each.value.network_bridge
    model       = "virtio"
    vlan_id     = each.value.network_tag
    firewall    = each.value.network_firewall
    mac_address = each.value.network_mac
  }

  # Mapped USB passthrough
  dynamic "usb" {
    for_each = try(each.value.usb_mappings, [])
    content {
      mapping = usb.value # Refers to the Proxmox Cluster USB mapping ID
    }
  }

  # Initialization Settings
  initialization {
    ip_config {
      ipv4 {
        address = each.value.ipv4_address
        gateway = each.value.ipv4_gateway
      }
    }

    dns {
      domain  = each.value.dns_domain
      servers = each.value.dns_servers
    }

    user_account {
      username = each.value.username
      password = each.value.password
      keys     = each.value.ssh_keys
    }

    upgrade      = false                    # Disable automatic package upgrades during initialization
    datastore_id = each.value.init_datatore # Datastore to save the temporary init drive/disk
  }

  # Terraform Lifecycle Settings
  started                              = each.value.vm_started
  reboot                               = false
  timeout_clone                        = 300
  timeout_create                       = 300
  timeout_migrate                      = 600
  timeout_reboot                       = 120
  timeout_start_vm                     = 120
  timeout_stop_vm                      = 120
  reboot_after_update                  = true
  stop_on_destroy                      = false
  purge_on_destroy                     = true
  delete_unreferenced_disks_on_destroy = false
}
