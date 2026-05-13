# Partial S3 backend — pass bucket/key/region at `terraform init`:
#   terraform init -reconfigure -backend-config=backend.ci.hcl
# Ephemeral / local experiments without remote state:
#   terraform init -reconfigure -backend=false
terraform {
  backend "s3" {}
}
