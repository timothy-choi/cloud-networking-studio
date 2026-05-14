variable "aws_region" {
  type        = string
  description = "AWS region for all resources."
}

variable "project_name" {
  type        = string
  description = "Short name prefix for resource Name tags (e.g. cns)."
}

variable "environment" {
  type        = string
  description = "Environment label (e.g. prod, staging)."
}

variable "key_name" {
  type        = string
  description = "Name of an existing EC2 key pair in this region (for SSH)."
}

variable "ssh_allowed_cidr" {
  type        = string
  description = <<-EOT
    CIDR allowed to reach SSH (port 22) on the instance security group.
    For laptops or fixed bastions, use your public IPv4 with /32 (e.g. 203.0.113.10/32).
    GitHub Actions hosted runners use unpredictable egress IPs — ephemeral CI in this repo sets 0.0.0.0/0 from the workflow (see docs/EPHEMERAL_CI_ENVIRONMENTS.md); tighten or use SSM Session Manager for production.
  EOT
}

variable "instance_type" {
  type        = string
  description = "EC2 instance type for the Compose host."
  default     = "t3.medium"
}

variable "vpc_cidr" {
  type        = string
  description = "IPv4 CIDR for the dedicated VPC."
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  type        = string
  description = "IPv4 CIDR for the single public subnet."
  default     = "10.0.1.0/24"
}

variable "ubuntu_version" {
  type        = string
  description = "Ubuntu release label for documentation; AMI is selected via ubuntu_ami_name_pattern. Use 22.04 with a jammy pattern if noble has no image in your region yet."
  default     = "24.04"
}

variable "ubuntu_ami_name_pattern" {
  type        = string
  description = "DescribeImages name wildcard for Canonical Ubuntu server AMIs (owner 099720109477). Broaden (e.g. hvm-ssd*) if gp3-only or legacy names differ by region."
  default     = "ubuntu/images/hvm-ssd*/ubuntu-noble-24.04-amd64-server-*"
}
