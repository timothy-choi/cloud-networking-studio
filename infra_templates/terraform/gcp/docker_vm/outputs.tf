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
  description = "Planned runtime host metadata (IPs assigned at apply time)."
  value = [
    for idx in range(var.vm_count) : {
      name       = var.vm_count > 1 ? "${var.instance_name}-${idx + 1}" : var.instance_name
      public_ip  = null
      private_ip = null
      ssh_user   = var.ssh_user
      ssh_port   = 22
      zone       = var.zone
    }
  ]
}

output "warnings" {
  description = "Plan review warnings."
  value = [
    "Plan-only: no resources will be created until apply is enabled in a future release.",
    "Ensure VPC network '${var.network_name}' exists in project '${var.project_id}'.",
  ]
}
