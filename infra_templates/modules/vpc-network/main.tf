variable "name" { type = string }
variable "region" { type = string }

output "network_id" {
  value = "net-${var.name}"
}

output "private_cidr" {
  value = "10.0.2.10"
}
