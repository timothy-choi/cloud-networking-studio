# Partial S3 backend — pass bucket/key/region at `terraform init`:
#   terraform init -input=false -reconfigure -backend-config=backend.ci.hcl
# CI sets TF_CLI_ARGS_init=-backend-config=backend.ci.hcl so the init line can stay as above without -backend-config on the CLI.
terraform {
  backend "s3" {}
}
