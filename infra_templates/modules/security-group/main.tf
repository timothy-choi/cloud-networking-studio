variable "name" { type = string }

output "firewall_id" {
  value = "fw-${var.name}"
}
