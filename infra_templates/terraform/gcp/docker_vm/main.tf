terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.40"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

locals {
  instance_tags = compact([for t in split(",", var.tags) : trimspace(t)])
  ssh_rule_name = "${var.instance_name}-allow-ssh"
  app_rule_name = "${var.instance_name}-allow-app"
}

resource "google_compute_firewall" "ssh" {
  name    = local.ssh_rule_name
  network = var.network_name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = [var.allowed_ssh_cidr]
  target_tags   = local.instance_tags
}

resource "google_compute_firewall" "app" {
  name    = local.app_rule_name
  network = var.network_name

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }

  source_ranges = [var.allowed_app_cidr]
  target_tags   = local.instance_tags
}

resource "google_compute_instance" "docker_vm" {
  count        = var.vm_count
  name         = var.vm_count > 1 ? "${var.instance_name}-${count.index + 1}" : var.instance_name
  machine_type = var.machine_type
  zone         = var.zone
  tags         = local.instance_tags

  labels = {
    cns_deployment = var.deployment_name
    cns_template   = var.cns_template
    cns_provider   = var.cns_provider
  }

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = 30
    }
  }

  network_interface {
    network = var.network_name

    access_config {}
  }

  metadata = {
    enable-oslogin = "FALSE"
    ssh-keys       = "${var.ssh_user}:${trimspace(var.ssh_public_key)}"
  }

  service_account {
    scopes = ["cloud-platform"]
  }
}
