variable "name" {
  type = string
}

variable "provider" {
  type = string
}

variable "region" {
  type = string
}

variable "zone" {
  type    = string
  default = ""
}

variable "ssh_user" {
  type = string
}

# Provider-specific modules are composed here; local/mock uses null_resource placeholders.

resource "null_resource" "vm" {
  triggers = {
    name     = var.name
    provider = var.provider
    region   = var.region
    zone     = var.zone
    ssh_user = var.ssh_user
  }
}

output "host" {
  value = {
    name       = var.name
    public_ip  = "203.0.113.50"
    private_ip = "10.0.1.50"
    ssh_user   = var.ssh_user
    ssh_port   = 22
    provider   = var.provider
    region     = var.region
  }
}
