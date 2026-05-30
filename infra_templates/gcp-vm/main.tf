variable "deployment_name" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "zone" {
  type    = string
  default = "us-central1-a"
}

variable "vm_count" {
  type    = number
  default = 1
}

variable "machine_type" {
  type    = string
  default = "e2-medium"
}

variable "ssh_user" {
  type    = string
  default = "ubuntu"
}

module "vm" {
  source   = "../modules/generic-vm"
  count    = var.vm_count
  name     = "${var.deployment_name}-gcp-${count.index + 1}"
  provider = "gcp"
  region   = var.region
  zone     = var.zone
  ssh_user = var.ssh_user
}

output "vm_count" {
  value = var.vm_count
}

output "region" {
  value = var.region
}

output "zone" {
  value = var.zone
}

output "hosts" {
  value = module.vm[*].host
}

output "exposed_ports" {
  value = [22, 80, 443]
}
