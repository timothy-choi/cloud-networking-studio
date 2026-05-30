# Local mock provider — no cloud API calls; produces deterministic inventory outputs.

terraform {
  required_version = ">= 1.5.0"
}

variable "deployment_name" {
  type        = string
  description = "Infrastructure deployment name"
}

variable "region" {
  type        = string
  default     = "local"
  description = "Logical region/zone label"
}

variable "vm_count" {
  type        = number
  default     = 1
  description = "Number of mock VMs to provision"
}

variable "ssh_user" {
  type        = string
  default     = "ubuntu"
  description = "SSH user for configured hosts"
}

resource "null_resource" "mock_vms" {
  count = var.vm_count

  triggers = {
    deployment_name = var.deployment_name
    index           = count.index
    region          = var.region
  }
}

output "vm_count" {
  value = var.vm_count
}

output "region" {
  value = var.region
}

output "hosts" {
  value = [
    for i in range(var.vm_count) : {
      name       = "${var.deployment_name}-vm-${i + 1}"
      public_ip  = "203.0.113.${10 + i}"
      private_ip = "10.0.0.${10 + i}"
      ssh_user   = var.ssh_user
      ssh_port   = 22
    }
  ]
}

output "exposed_ports" {
  value = [22, 80, 443]
}
