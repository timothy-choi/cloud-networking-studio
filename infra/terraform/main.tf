provider "aws" {
  region = var.aws_region
  # Avoid slow IMDS (169.254.169.254) lookups when running Terraform on a laptop — use ~/.aws/credentials, env vars, or SSO instead.
  skip_metadata_api_check = true

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}
