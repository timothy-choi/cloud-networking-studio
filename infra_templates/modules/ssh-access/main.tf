variable "name" { type = string }
variable "ssh_user" { type = string }

output "ssh_user" {
  value = var.ssh_user
}
