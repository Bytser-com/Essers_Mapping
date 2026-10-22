terraform {
  required_version = ">= 1.5.0" # Ensures you are using a modern version of Terraform

  # Path defaults to ./terraform.tfstate; CI overrides it with -backend-config="path=..."
  backend "local" {}

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "~> 0.111.0" # Clean version pinning for stability
    }
  }
}

provider "proxmox" {
  endpoint = var.proxmox_api_url
  insecure = var.proxmox_api_insecure # Set to false if you have real SSL certificates
  # Either use username/password or API token for authentication.
  #username = var.proxmox_api_username
  #password = var.proxmox_api_password
  api_token = var.proxmox_api_token

  ssh {
    agent    = true
    username = "root" # required when using api_token
    # Either use password or private_key for SSH authentication.
    password = var.proxmox_ssh_password # required when using api_token
    #private_key = trimspace(var.proxmox_ssh_private_key) # required when using api_token
  }
}
