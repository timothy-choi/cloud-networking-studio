variable "name" {
  type = string
}

variable "provider" {
  type = string
}

variable "region" {
  type = string
}

variable "ssh_user" {
  type = string
}

module "network" {
  source = "../vpc-network"
  name   = "${var.name}-net"
  region = var.region
}

module "firewall" {
  source = "../security-group"
  name   = "${var.name}-fw"
}

module "ssh" {
  source   = "../ssh-access"
  name     = var.name
  ssh_user = var.ssh_user
}

resource "null_resource" "docker_vm" {
  triggers = {
    name     = var.name
    provider = var.provider
    region   = var.region
    network  = module.network.network_id
    firewall = module.firewall.firewall_id
  }
}

output "host" {
  value = {
    name       = var.name
    public_ip  = "203.0.113.60"
    private_ip = module.network.private_cidr
    ssh_user   = var.ssh_user
    ssh_port   = 22
    provider   = var.provider
    region     = var.region
    docker     = true
  }
}
