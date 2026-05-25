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

# --- Optional RDS PostgreSQL (production persistence; EC2 Compose uses external DATABASE_URL) ---

variable "rds_enabled" {
  type        = bool
  description = "When true, provision AWS RDS PostgreSQL in the VPC and expose outputs for DATABASE_URL on EC2. Ephemeral/CI keep Docker Postgres unless you enable this explicitly."
  default     = false
}

variable "rds_instance_class" {
  type        = string
  description = "RDS instance class (e.g. db.t4g.micro, db.t3.micro)."
  default     = "db.t4g.micro"
}

variable "rds_allocated_storage" {
  type        = number
  description = "Allocated storage (GiB) for the RDS instance."
  default     = 20
}

variable "rds_publicly_accessible" {
  type        = bool
  description = "When true, RDS gets a public DNS endpoint (still SG-restricted to the EC2 SG on 5432). Use false for VPC-only access from EC2."
  default     = false
}

variable "rds_master_username" {
  type        = string
  description = "Master username for RDS (must match DATABASE_URL user on EC2)."
  default     = "cns_user"
}

variable "rds_master_password" {
  type        = string
  sensitive   = true
  description = "Master password for RDS. Leave empty to auto-generate (stored in Terraform state). Prefer TF_VAR_rds_master_password from GitHub Actions secrets (POSTGRES_PASSWORD or RDS_PASSWORD)."
  default     = ""
}

variable "rds_database_name" {
  type        = string
  description = "Initial database name on RDS (matches docker-compose default DB name)."
  default     = "cloud_networking_studio"
}

variable "rds_backup_retention_period" {
  type        = number
  description = "Automated backup retention in days (0 disables automated backups)."
  default     = 7
}

variable "rds_deletion_protection" {
  type        = bool
  description = "When true, RDS cannot be deleted without disabling this flag first."
  default     = false
}

variable "public_subnet_b_cidr" {
  type        = string
  description = "Second public subnet CIDR (different AZ) for RDS DB subnet group when rds_enabled."
  default     = "10.0.2.0/24"
}

# --- Staging EC2 bootstrap (environment=staging only) ---

variable "staging_cors_origins" {
  type        = string
  description = "Default CNS_CORS_ORIGINS written to ~/cloud-networking-studio-staging/.env.staging on first boot and merged on deploy."
  default     = "https://app-staging.cloudnetstudio.com,https://cloud-networking-studio.vercel.app"
}

variable "staging_api_host" {
  type        = string
  description = "Staging API hostname for Caddy/TLS bootstrap (no scheme)."
  default     = "api-staging.cloudnetstudio.com"
}

variable "staging_app_url" {
  type        = string
  description = "Staging SPA origin URL for CNS_FRONTEND_APP_URL bootstrap."
  default     = "https://app-staging.cloudnetstudio.com"
}

variable "staging_remote_docker_ssh_key_path" {
  type        = string
  description = "Host path to the remote_docker SSH private key; written to .env.staging as CNS_REMOTE_DOCKER_SSH_KEY_PATH on first boot."
  default     = "/opt/cns/secrets/remote_docker_ssh.pem"
}
