variable "deployment_name" {
  type = string
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "vm_count" {
  type    = number
  default = 1
}

variable "instance_type" {
  type    = string
  default = "t3.medium"
}

variable "ssh_user" {
  type    = string
  default = "ubuntu"
}

module "vm" {
  source   = "../modules/generic-vm"
  count    = var.vm_count
  name     = "${var.deployment_name}-aws-${count.index + 1}"
  provider = "aws"
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
  value = module.vm[*].host
}

output "exposed_ports" {
  value = [22, 80, 443]
}
