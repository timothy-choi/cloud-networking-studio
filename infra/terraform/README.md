# Terraform — Cloud Networking Studio (AWS)

This directory provisions a **small dedicated VPC**, **two public subnets** (two AZs; second is for an optional **RDS** DB subnet group), **security groups**, an **Ubuntu 24.04 EC2** instance (Docker Engine + Compose plugin pre-installed via `user_data`), and an **Elastic IP** for a stable public address. Application containers are started separately (`docker compose` on the instance, or via CI over SSH). Optional **RDS PostgreSQL** is controlled by **`rds_enabled`** (see [docs/RDS.md](../../docs/RDS.md)). See [docs/DEPLOYMENT.md](../../docs/DEPLOYMENT.md), [docs/CICD_DEPLOYMENT.md](../../docs/CICD_DEPLOYMENT.md), and [docs/EPHEMERAL_CI_ENVIRONMENTS.md](../../docs/EPHEMERAL_CI_ENVIRONMENTS.md).

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

`backend.tf` declares a partial **`backend "s3" {}`** (merged with `versions.tf`). For **durable production** state (required by `.github/workflows/deploy-production.yml`), configure an S3 bucket and run init with a backend config file. Example template: **`backend.s3.hcl.example`**.

```bash
cd infra/terraform
cp backend.s3.hcl.example backend.local.hcl   # edit bucket/key — keep backend.local.hcl gitignored
terraform init -reconfigure -backend-config=backend.local.hcl
```

For **throwaway** local runs without S3, you can use **local state** (not used in GitHub Actions):

```bash
terraform init -input=false -reconfigure -backend=false
```

Ephemeral **CI** uses **S3** with a per-run object key under **`TF_STATE_BUCKET`** (see **`.github/workflows/ephemeral-infra-smoke.yml`**).

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
terraform init -input=false -reconfigure -backend-config=backend.local.hcl   # or another generated backend.*.hcl
terraform fmt -recursive
terraform validate
terraform plan
terraform apply
```

- **`terraform init`** — downloads providers (**AWS**, **random**) and creates `.terraform/` (ignored by git).
- **`terraform fmt`** — normalizes formatting (run after edits).
- **`terraform validate`** — static checks (run after `init`).
- **`terraform plan`** — shows the execution plan (requires valid AWS credentials).
- **`terraform apply`** — provisions resources; confirm when prompted.

After apply, read outputs:

```bash
terraform output
```

## SSH and deploy the app

Networking: the instance is in a **public subnet** with **`map_public_ip_on_launch`**, a **default route** to the **internet gateway** (`network.tf`), **`associate_public_ip_address`**, and an **Elastic IP** (`ec2.tf`), so **`terraform output -raw public_ip`** is reachable on **22 / 80 / 443** once the instance is up. SSH ingress is restricted to **`var.ssh_allowed_cidr`** (`security.tf`); use **`MY_PUBLIC_IP/32`** from **`terraform.tfvars`** for day-to-day access. GitHub Actions ephemeral CI uses **`0.0.0.0/0`** in the workflow only for that job (see **`docs/EPHEMERAL_CI_ENVIRONMENTS.md`**).

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

Removes the VPC, instance, EIP, and related resources. **Data loss:** anything only on the instance disk is gone; **RDS** (if enabled) is **not** destroyed by default when managed in the same state — check `rds_deletion_protection` and run **`terraform destroy`** only after snapshots or when you intend to drop the database. Use backups or external volumes if you need durability beyond this lab template.

**Production:** the `deploy-production` GitHub Action **never** runs `terraform destroy`. Only this manual command (or a dedicated workflow you add) removes prod infra.

**Ephemeral CI:** `.github/workflows/ephemeral-infra-smoke.yml` runs **`terraform destroy -auto-approve`** in an **`always()`** step after tests.

## Outputs reference

| Output | Meaning |
|--------|---------|
| `public_ip` | Elastic IP (stable) |
| `security_group_id` | Instance security group (SSH from `ssh_allowed_cidr`) |
| `subnet_id` | Public subnet (IGW default route) |
| `vpc_id` | VPC for the stack |
| `public_url` | `http://<public_ip>` |
| `sslip_host` | `<public_ip>.sslip.io` hostname |
| `stack_base_url_sslip` | `https://<public_ip>.sslip.io` — optional HTTPS origin (ACME on sslip can be flaky) |
| `stack_base_url_sslip_http` | `http://<public_ip>.sslip.io` — **`CNS_BASE_URL`** for **production + ephemeral** smoke (`deploy-production.yml` / ephemeral) |
| `api_base_url_sslip` | `https://<public_ip>.sslip.io/api` — use with **`VERCEL_VITE_API_BASE_URL`** when serving HTTPS API from EC2 |
| `api_base_url_sslip_http` | `http://<public_ip>.sslip.io/api` — default **`VITE_API_BASE_URL`** in CI when **`VERCEL_VITE_API_BASE_URL`** unset (HTTP API; **mixed content** if Vercel page is HTTPS — set the secret for real HTTPS API). |
| `ssh_command` | Example `ssh` line (adjust key path) |
| `instance_id` | EC2 instance ID for support / debugging |
| `rds_address` | RDS hostname when `rds_enabled` (else empty); use in `DATABASE_URL` on EC2 |
| `rds_port` | RDS port when enabled (else empty; use **5432** when connecting) |
| `rds_database_name` | RDS database name when enabled (else empty) |
| `rds_username` | RDS master username when enabled (else empty); password is **never** an output |

## Lock file

After `terraform init`, Terraform may create **`.terraform.lock.hcl`**. Committing it is recommended so everyone uses the same provider versions. It is **not** listed in `.gitignore` here.

## Validation (CI / local)

```bash
cd infra/terraform
terraform init -input=false -reconfigure -backend-config=backend.local.hcl
terraform fmt -check -recursive
terraform validate
terraform plan -input=false
```

`plan` requires AWS credentials and may show a non-empty diff; `-input=false` avoids prompts in automation.
