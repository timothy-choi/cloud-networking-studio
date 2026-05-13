terraform {
  required_version = ">= 1.5.0"

  # Partial config: supply bucket/key/region via `terraform init -backend-config=...` in CI,
  # or use `terraform init -backend=false` for ephemeral runs and local experiments.
  backend "s3" {}

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
