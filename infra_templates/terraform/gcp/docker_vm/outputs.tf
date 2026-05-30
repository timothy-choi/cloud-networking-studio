output "vm_count" {
  description = "Planned VM count."
  value       = var.vm_count
}

output "region" {
  description = "Deployment region."
  value       = var.region
}

output "zone" {
  description = "Deployment zone."
  value       = var.zone
}

output "machine_type" {
  description = "Compute machine type."
  value       = var.machine_type
}

output "network_name" {
  description = "VPC network name."
  value       = var.network_name
}

output "instance_name" {
  description = "Primary instance name."
  value       = google_compute_instance.docker_vm[0].name
}

output "public_ip" {
  description = "Primary instance public IP."
  value       = try(google_compute_instance.docker_vm[0].network_interface[0].access_config[0].nat_ip, null)
}

output "private_ip" {
  description = "Primary instance private IP."
  value       = try(google_compute_instance.docker_vm[0].network_interface[0].network_ip, null)
}

output "ssh_user" {
  description = "Configured SSH user."
  value       = var.ssh_user
}

output "exposed_ports" {
  description = "TCP ports exposed by firewall rules."
  value       = [22, 80, 443]
}

output "firewall_rules" {
  description = "Planned firewall rule names."
  value = [
    google_compute_firewall.ssh.name,
    google_compute_firewall.app.name,
  ]
}

output "estimated_resources" {
  description = "High-level resource summary for plan review."
  value = {
    compute_instances = var.vm_count
    firewall_rules    = 2
    network           = var.network_name
  }
}

output "hosts" {
  description = "Runtime host metadata from Terraform outputs."
  value = [
    for inst in google_compute_instance.docker_vm : {
      name       = inst.name
      public_ip  = try(inst.network_interface[0].access_config[0].nat_ip, null)
      private_ip = try(inst.network_interface[0].network_ip, null)
      ssh_user   = var.ssh_user
      ssh_port   = 22
      zone       = var.zone
    }
  ]
}

output "warnings" {
  description = "Plan/apply review warnings."
  value = [
    "This template creates billable GCP resources when applied.",
    "Ensure VPC network '${var.network_name}' exists in project '${var.project_id}'.",
  ]
}
