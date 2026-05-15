# Ephemeral CI environments (PR Terraform)

**Step 31 context:** This workflow is **only for pull requests (same repo) and manual runs**. It is **not** the production `main` deploy. It provisions **temporary** AWS resources, deploys the app, smoke-tests over **HTTP**, then **always destroys** Terraform state and infra.

The workflow **`.github/workflows/ephemeral-infra-smoke.yml`** provisions a **short-lived** Terraform stack (VPC, EC2, EIP), deploys **`docker-compose.prod.yml` + `docker-compose.sslip.yml`**, writes **`.env`** on the instance (including **`CADDYFILE_SSLIP=./deploy/Caddyfile.prod`** so Caddy serves **HTTP :80** only on sslip), runs **`scripts/prod_smoke_test.sh`** against **`http://<EIP>.sslip.io`**, then runs **`terraform destroy`** with **`if: always()`**.

## How it differs from production (`main`)

| | **Production** (`deploy-production.yml`, push **`main`**) | **Ephemeral** (this workflow) |
|--|----------------------------------------|------------------------|
| **Trigger** | `push` to `main`, `workflow_dispatch` | `pull_request`, `workflow_dispatch` |
| **Terraform state** | **S3**, fixed key (default `…/prod/terraform.tfstate`) | **S3**, **unique** key `cloud-networking-studio/ephemeral/<run_id>/terraform.tfstate` |
| **`terraform destroy`** | **Never** — EC2/VPC/EIP stay for the next deploy | **`always()`** after smoke |
| **EC2 `.env`** | Written each deploy: HTTPS Caddy (**`Caddyfile.sslip`**, **`CNS_CADDY_AUTO_HTTPS=on`**, sslip host) + secrets | Generated on each run (random Postgres password + **HTTP-only** Caddy vars) |
| **Compose directory** | `~/cloud-networking-studio` | `~/cloud-networking-studio-ephemeral` (fresh clone) |
| **SSH ingress (22)** | Secret **`TF_VAR_SSH_ALLOWED_CIDR`** (often **`MY_IP/32`**) | **`TF_VAR_ssh_allowed_cidr` = `0.0.0.0/0`** for GitHub-hosted runners |
| **Vercel** | Yes — after EC2 smoke | **No** — no Vercel secrets required |

**Why PR and `main` differ:** `main` targets a **long-lived** production instance and must **not** tear down VPC/EC2. PRs use an **isolated** stack and **must** destroy it to control cost and avoid orphaned resources.

## SSH from GitHub Actions vs your laptop

- **Local / manual Terraform or SSH:** set **`ssh_allowed_cidr`** in **`terraform.tfvars`** to **your public IPv4 `/32`**.
- **Ephemeral workflow:** sets **`TF_VAR_ssh_allowed_cidr` to `0.0.0.0/0`** so **GitHub-hosted runners** can reach port 22 (runner egress IPs are not static). This is **broad exposure** while the instance exists.
- **Production deploy** uses **`TF_VAR_SSH_ALLOWED_CIDR`** from repository secrets. If Actions cannot reach port 22, widen CIDR or use SSM later.

After **`terraform apply`**, the job waits until **TCP port 22** is reachable, then runs **`appleboy/ssh-action`**.

## Lifecycle

1. **Terraform apply** (single `run:` block): **`backend.ci.hcl`**, **`terraform init`**, **`validate`**, **`plan`**, **`apply`**, **`terraform output`** (including **`stack_base_url_sslip_http`** for smoke).
2. **Wait for SSH** (poll, ~5 min max).
3. **SSH:** **`cloud-init`**, **Docker** if needed, clone/checkout, **`.env`** (heredoc), **`docker compose … up`** (logs only on **config** / **up** failure).
4. **Smoke:** **`prod_smoke_test.sh`** with **`CNS_BASE_URL`** = **`stack_base_url_sslip_http`**.
5. **Optional heavy smoke** (`continue-on-error: true`).
6. **`terraform destroy`** with **`if: always()`**, same state key as apply.

`hashicorp/setup-terraform` uses **`terraform_wrapper: false`**.

If **destroy** fails, resources may linger — re-run the workflow or clean up in AWS.

## Fork pull requests

Jobs are **skipped** when `github.event.pull_request.head.repo.full_name != github.repository` so untrusted code cannot access your repository secrets.

## Cost warning

Each run creates an **EC2 instance**, **Elastic IP**, and **VPC** for a few minutes. Frequent PRs **incur AWS charges**.

## Secrets (GitHub) — ephemeral job

| Secret | Purpose |
|--------|---------|
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` | Terraform AWS provider |
| `TF_STATE_BUCKET` | S3 bucket for Terraform state (same bucket as production; **different key** per run) |
| Optional `TF_STATE_DYNAMODB_TABLE` | State locking |
| `TF_VAR_KEY_NAME` | EC2 key pair name |
| `EC2_SSH_PRIVATE_KEY`, `EC2_SSH_USER` | SSH to the ephemeral instance |

**Not required here:** `POSTGRES_PASSWORD`, `CNS_CORS_ORIGINS`, Vercel tokens (ephemeral generates Postgres locally and does not deploy Vercel).

**Production `main` additionally needs:** `POSTGRES_PASSWORD`, `CNS_CORS_ORIGINS`, Vercel secrets, and optional **`VERCEL_VITE_API_BASE_URL`** — see **`docs/CICD_DEPLOYMENT.md`**.
