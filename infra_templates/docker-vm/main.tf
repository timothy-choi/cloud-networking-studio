variable "deployment_name" {
  type = string
}

variable "provider" {
  type    = string
  default = "local"
}

variable "region" {
  type    = string
  default = "local"
}

variable "vm_count" {
  type    = number
  default = 1
}

variable "ssh_user" {
  type    = string
  default = "ubuntu"
}

module "docker_vm" {
  source   = "../modules/docker-vm"
  count    = var.vm_count
  name     = "${var.deployment_name}-docker-${count.index + 1}"
  provider = var.provider
  region   = var.region
  ssh_user = var.ssh_user
}

output "vm_count" {
  value = var.vm_count
}

output "region" {
  value = var.region
}

output "hosts" {
  value = module.docker_vm[*].host
}

output "exposed_ports" {
  value = [22, 2375, 80, 443]
}
