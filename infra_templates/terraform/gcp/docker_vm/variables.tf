variable "deployment_name" {
  type        = string
  description = "CNS infrastructure deployment name (used for labeling)."
}

variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "region" {
  type        = string
  description = "GCP region."
}

variable "zone" {
  type        = string
  description = "GCP zone for the compute instance."
}

variable "machine_type" {
  type        = string
  description = "Compute Engine machine type."
  default     = "e2-medium"
}

variable "network_name" {
  type        = string
  description = "VPC network name (must already exist)."
  default     = "default"
}

variable "instance_name" {
  type        = string
  description = "Base name for the compute instance."
}

variable "ssh_user" {
  type        = string
  description = "Linux user for SSH access."
  default     = "ubuntu"
}

variable "ssh_public_key" {
  type        = string
  description = "OpenSSH public key installed for ssh_user (injected by CNS from server env)."
  sensitive   = true

  validation {
    condition     = length(trimspace(var.ssh_public_key)) > 0
    error_message = "ssh_public_key is required for CNS-managed SSH access."
  }
}

variable "allowed_ssh_cidr" {
  type        = string
  description = "CIDR allowed for SSH (tcp/22)."
}

variable "allowed_app_cidr" {
  type        = string
  description = "CIDR allowed for HTTP/HTTPS application traffic."
}

variable "tags" {
  type        = string
  description = "Comma-separated network tags applied to the instance and firewall rules."
  default     = "cns-docker-vm"
}

variable "vm_count" {
  type        = number
  description = "Number of Docker-ready VMs to plan (max enforced by CNS)."
  default     = 1
}
