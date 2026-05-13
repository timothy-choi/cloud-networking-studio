# Terraform — Cloud Networking Studio (AWS)

This directory provisions a **small dedicated VPC**, a **public subnet**, a **security group**, an **Ubuntu 24.04 EC2** instance (Docker Engine + Compose plugin pre-installed via `user_data`), and an **Elastic IP** for a stable public address. Application containers are started separately (`docker compose` on the instance, or via CI over SSH). See [docs/DEPLOYMENT.md](../../docs/DEPLOYMENT.md), [docs/CICD_DEPLOYMENT.md](../../docs/CICD_DEPLOYMENT.md), and [docs/EPHEMERAL_CI_ENVIRONMENTS.md](../../docs/EPHEMERAL_CI_ENVIRONMENTS.md).

## Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) **1.5+**
- An [AWS account](https://aws.amazon.com/) and **credentials configured for the CLI/SDK** (see below)
- An **existing EC2 key pair** in the target region (for SSH)
- A sensible **`ssh_allowed_cidr`** (your public IPv4 `/32` is recommended for interactive SSH; CI may use a broader lab CIDR — see ephemeral docs)

### AWS credentials (required for `plan` / `apply`)

Terraform uses the default AWS credential chain. On your **Mac or dev machine**, configure one of:

- **`aws configure`** — writes `~/.aws/credentials` and `~/.aws/config`
- **`AWS_PROFILE`** — e.g. `export AWS_PROFILE=my-profile` then run `terraform plan`
- **`AWS_ACCESS_KEY_ID`** and **`AWS_SECRET_ACCESS_KEY`** (and optional `AWS_SESSION_TOKEN`) — short-lived or CI keys

The provider is set with **`skip_metadata_api_check = true`** so Terraform does not wait on the EC2 instance metadata service (`169.254.169.254`), which is unavailable off AWS and caused noisy timeouts.

If you still see “No valid credential sources found”, no profile/env credentials are loaded yet — fix that before re-running `terraform plan`.

## Remote state (production / shared CI)

`versions.tf` declares a partial **`backend "s3" {}`**. For **durable production** state (required by `.github/workflows/deploy-production.yml`), configure an S3 bucket and run init with a backend config file. Example template: **`backend.s3.hcl.example`**.

```bash
cd infra/terraform
cp backend.s3.hcl.example backend.local.hcl   # edit bucket/key — keep backend.local.hcl gitignored
terraform init -backend-config=backend.local.hcl
```

For **throwaway** runs (local lab or **ephemeral PR** CI), use **local state**:

```bash
terraform init -backend=false
```

Ephemeral CI always **`terraform destroy`** at the end of the job; local state on the runner is discarded.

## Configure variables

1. Copy the example tfvars file:

   ```bash
   cd infra/terraform
   cp terraform.tfvars.example terraform.tfvars
   ```

2. Edit **`terraform.tfvars`** with your `aws_region`, `key_name`, `ssh_allowed_cidr`, `project_name`, optional `instance_type`, and optional **`ubuntu_ami_name_pattern`** (see Ubuntu AMI below).

3. **Never commit** `terraform.tfvars`, state files, or private keys. The repo root `.gitignore` ignores `infra/terraform/*.tfvars` except `terraform.tfvars.example`.

### Ubuntu AMI lookup

AMIs are owned by **Canonical** (`099720109477`). The default **`ubuntu_ami_name_pattern`** is broad enough to match both legacy **`hvm-ssd`** and newer **`hvm-ssd-gp3`** noble image names in most regions.

If **`data.aws_ami.ubuntu` returns no results** in a given region (newer partitions or delayed publishes), set in `terraform.tfvars`:

- **`ubuntu_ami_name_pattern = "ubuntu/images/hvm-ssd*/ubuntu-jammy-22.04-amd64-server-*"`** and **`ubuntu_version = "22.04"`** to use **Ubuntu 22.04 LTS (jammy)** instead.

You can also paste a specific prefix you see in the EC2 “Launch instance” AMI picker after narrowing to Ubuntu Server 24.04/22.04 amd64.

## Commands

From **`infra/terraform/`**:

```bash
terraform init -backend=false   # or -backend-config=... for S3
terraform fmt -recursive
terraform validate
terraform plan
terraform apply
```

- **`terraform init`** — downloads the AWS provider and creates `.terraform/` (ignored by git).
- **`terraform fmt`** — normalizes formatting (run after edits).
- **`terraform validate`** — static checks (run after `init`).
- **`terraform plan`** — shows the execution plan (requires valid AWS credentials).
- **`terraform apply`** — provisions resources; confirm when prompted.

After apply, read outputs:

```bash
terraform output
```

## SSH and deploy the app

1. SSH (default user on Ubuntu AMIs is **`ubuntu`**):

   ```bash
   ssh -i ~/.ssh/your-key.pem ubuntu@$(terraform output -raw public_ip)
   ```

2. Clone the repository and start the production stack (from repo root on the instance). For **HTTPS + sslip.io** (Vercel split or public API URL):

   ```bash
   sudo apt-get update && sudo apt-get install -y git
   git clone https://github.com/<your-org>/cloud-networking-studio.git
   cd cloud-networking-studio
   cp .env.example .env
   # edit .env — set POSTGRES_PASSWORD, CNS_CORS_ORIGINS (include Vercel origins), SSLIP_HOST=<EIP>.sslip.io
   docker compose -f docker-compose.prod.yml -f docker-compose.sslip.yml up -d --build
   ```

   For **HTTP only** on port 80 (unchanged default):

   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```

3. Open **`http://<Elastic IP>`** or **`https://<Elastic IP>.sslip.io`** once Caddy and services are healthy.

For a fuller EC2 checklist, see [docs/EC2_RUNBOOK.md](../../docs/EC2_RUNBOOK.md).

## Destroy

```bash
terraform destroy
```

Removes the VPC, instance, EIP, and related resources. **Data loss:** anything only on the instance disk is gone; use backups or external volumes if you need durability beyond this lab template.

**Production:** the `deploy-production` GitHub Action **never** runs `terraform destroy`. Only this manual command (or a dedicated workflow you add) removes prod infra.

**Ephemeral CI:** `.github/workflows/ephemeral-infra-smoke.yml` runs **`terraform destroy -auto-approve`** in an **`always()`** step after tests.

## Outputs reference

| Output | Meaning |
|--------|---------|
| `public_ip` | Elastic IP (stable) |
| `public_url` | `http://<public_ip>` |
| `sslip_host` | `<public_ip>.sslip.io` hostname |
| `stack_base_url_sslip` | `https://<public_ip>.sslip.io` — use as **`CNS_BASE_URL`** for smoke scripts |
| `api_base_url_sslip` | `https://<public_ip>.sslip.io/api` — use as **`VITE_API_BASE_URL`** for Vercel builds |
| `ssh_command` | Example `ssh` line (adjust key path) |
| `instance_id` | EC2 instance ID for support / debugging |

## Lock file

After `terraform init`, Terraform may create **`.terraform.lock.hcl`**. Committing it is recommended so everyone uses the same provider versions. It is **not** listed in `.gitignore` here.

## Validation (CI / local)

```bash
cd infra/terraform
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
terraform plan -input=false
```

`plan` requires AWS credentials and may show a non-empty diff; `-input=false` avoids prompts in automation.
