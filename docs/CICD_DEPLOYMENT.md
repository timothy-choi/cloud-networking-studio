# CI/CD: production deployment (Vercel + EC2)

This document describes how **GitHub Actions** can deploy **Cloud Networking Studio** in the split layout from Step 30:

- **Browser UI:** Vercel (static Vite build). Users bookmark and share only the Vercel URL.
- **Control-plane API:** Terraform-managed **EC2** running `docker-compose.prod.yml` plus **`docker-compose.sslip.yml`**, with HTTPS on **`https://<Elastic IP>.sslip.io`** and paths under **`/api/*`** routed to FastAPI.
- **Why the API URL is “hidden”:** The Vercel build bakes **`VITE_API_BASE_URL`** (at build time) to the sslip API base. The SPA calls the EC2 origin from JavaScript; users do not need to type the EC2/sslip URL unless they open devtools or share API links.

## Architecture (high level)

```mermaid
flowchart LR
  subgraph users [Users]
    B[Browser]
  end
  subgraph vercel [Vercel]
    UI[Static SPA]
  end
  subgraph aws [AWS EC2]
    C[Caddy TLS sslip]
    F[Frontend container optional]
    A[FastAPI]
  end
  B --> UI
  UI -->|"fetch() JSON"| C
  C -->|"/api/* stripped"| A
```

- **Vercel** serves the SPA and handles client-side routing (`frontend/vercel.json` rewrites).
- **EC2 Caddy** terminates TLS for `*.sslip.io` and proxies **`/api/*`** to the backend (same behavior as HTTP-only `deploy/Caddyfile.prod` on port 80).

## Vercel project settings

| Setting | Value |
|--------|--------|
| Root directory | `frontend` |
| Build command | `npm run build` (CI uses `vercel build` with the same env; see workflow) |
| Output directory | `dist` |
| Environment variable (Production) | `VITE_API_BASE_URL` = `https://<EIP>.sslip.io/api` (no trailing slash after `api`) |

Example:

```bash
VITE_API_BASE_URL=https://203.0.113.7.sslip.io/api
```

Copy **`frontend/.env.example`** when developing against a remote API.

## Terraform and durable state

The **Deploy production** workflow (`.github/workflows/deploy-production.yml`) runs **`terraform apply`** on every push to **`main`**. To **reuse** the same EC2/VPC/EIP across runs, Terraform state must live in a **remote backend** (recommended: **S3**).

1. Create an S3 bucket (and optionally a DynamoDB table for state locking).
2. Add repository secret **`TF_STATE_BUCKET`** (required for that workflow).
3. Optional: **`TF_STATE_KEY`** (defaults to `cloud-networking-studio/prod/terraform.tfstate`).
4. Optional: **`TF_STATE_DYNAMODB_TABLE`** for lock coordination.

The repo declares a partial **`backend "s3" {}`** in `infra/terraform/backend.tf` (merged with `versions.tf`). Local developers can use:

- `terraform init -backend-config=backend.local.hcl` (see `backend.s3.hcl.example`), or  
- `terraform init -input=false -reconfigure -backend-config=backend.local.hcl` for a dedicated non-CI state file.

**The production workflow does not run `terraform destroy`.** Destroy is manual or a separate process.

## EC2 bootstrap and `.env`

**GitHub Actions (`deploy-production.yml`):** before SSH deploy, the workflow checks repository secrets **`POSTGRES_PASSWORD`** and **`CNS_CORS_ORIGINS`**. On the instance, if **`~/cloud-networking-studio/.env` does not exist**, the SSH step creates it from those secrets (plus **`CNS_ENVIRONMENT=production`**, **`CNS_CONTROLLER_MODE=manual`**, matching **`DATABASE_URL`**, and **`SSLIP_HOST`** for sslip). Secret values are **not** written to logs (`set -x` is avoided on the remote script). If **`.env` already exists** (manual install), the workflow **only refreshes `SSLIP_HOST`** so your local passwords and CORS stay in place.

**Manual / local EC2:** copy **`.env.example`** to **`.env`** and set at least:

- Strong **`POSTGRES_PASSWORD`** (and matching **`DATABASE_URL`** if you override it).
- **`CNS_CORS_ORIGINS`** including your **Vercel production origin** (and any preview origins you care about), **`https://<EIP>.sslip.io`**, and local dev URLs as needed.
- Optional **`CNS_CORS_ORIGIN_REGEX`** for patterns such as Vercel preview hosts (see `backend/.env.example`).

**`docker-compose.prod.yml`** reads **`POSTGRES_*`**, **`DATABASE_URL`**, **`CNS_*`**, etc. from **`.env`** when you pass **`--env-file .env`** (as the workflow does).

The workflow **appends or refreshes `SSLIP_HOST=<EIP>.sslip.io`** on each deploy and runs:

```bash
sudo docker compose -f docker-compose.prod.yml -f docker-compose.sslip.yml --env-file .env up -d --build
```

Plain **`docker-compose.prod.yml`** alone remains valid for **HTTP-only** local or EC2 setups (`deploy/Caddyfile.prod`).

## GitHub Actions: `deploy-production.yml`

On **`push` to `main`** (and **`workflow_dispatch`**), the **`deploy`** job:

1. Runs **backend pytest** (with Postgres service on the runner).
2. Validates **`docker-compose.prod.yml`** via `docker compose config`.
3. Builds the **frontend** once with default Vite env (sanity compile before cloud steps).
4. Runs a **single shell step** under **`infra/terraform`**: writes **`backend.ci.hcl`**, **`rm -rf .terraform`**, **`terraform init -input=false -reconfigure`** (with **`TF_CLI_ARGS_init=-backend-config=backend.ci.hcl`** so the partial S3 backend is configured), then **`fmt -check`**, **`validate`**, **`plan`**, **`apply`**, then **`terraform output`** in the same step.
5. **Debug (pre-SSH):** prints **`terraform output`**, **`steps.tf.outputs.public_ip`**, and **`security_group_id`**, **`subnet_id`**, **`vpc_id`** (Terraform outputs).
6. **Wait for SSH:** polls until **TCP port 22** on **`public_ip`** accepts connections (instance is in a **public subnet** with **`map_public_ip_on_launch`**, default route to the **internet gateway**, and an **Elastic IP** — see `infra/terraform/network.tf` and `ec2.tf`).
7. **Require EC2 deploy secrets:** fails early if **`POSTGRES_PASSWORD`** or **`CNS_CORS_ORIGINS`** repository secrets are unset (values are never printed).
8. **SSH** (`appleboy/ssh-action`) to the instance: **`sudo cloud-init status --wait`**, ensure **Docker** (install from Docker’s apt repo if still missing), **`sudo docker compose`**, then clone or update repo, **`git checkout` the pushed SHA**, create **`.env` from secrets if missing** (else refresh **`SSLIP_HOST`** only), bring up **Compose + sslip overlay**.
9. Runs **`scripts/prod_smoke_test.sh`** with **`CNS_BASE_URL=${stack_base_url_sslip}`** (waits longer for ACME via **`CNS_WAIT_ATTEMPTS`**).
10. Runs **`vercel pull` / `vercel build` / `vercel deploy --prebuilt --prod`** with **`VITE_API_BASE_URL`** set to **`api_base_url_sslip`**.

**SSH CIDR:** for **local or manual** Terraform, use **`ssh_allowed_cidr = "<MY_PUBLIC_IP>/32"`** in **`terraform.tfvars`**. For **`deploy-production.yml`**, set secret **`TF_VAR_SSH_ALLOWED_CIDR`** to **`MY_IP/32`** when only you SSH from home, or to **`0.0.0.0/0`** only if GitHub Actions must reach port 22 and you accept world-writable SSH for the lifetime of the rule (prefer **AWS SSM Session Manager** later to drop open SSH). **Ephemeral** workflow forces **`0.0.0.0/0`** in YAML (see **`docs/EPHEMERAL_CI_ENVIRONMENTS.md`**).

`hashicorp/setup-terraform` is used only to install the Terraform CLI with **`terraform_wrapper: false`** so all **`terraform`** invocations run in plain shell blocks.

## CORS

Browsers load the SPA from **Vercel** (`https://*.vercel.app`) but call the API on **`https://<EIP>.sslip.io`** — that is **cross-origin**. FastAPI must allow the **Vercel** origin(s) via:

- **`CNS_CORS_ORIGINS`** — e.g. `https://your-project.vercel.app`, `http://localhost:5174`, …
- **`CNS_CORS_ORIGIN_REGEX`** (optional) — e.g. `^https://.*\.vercel\.app$` for previews (tighten to your org policy).

You typically **do not** add the sslip URL as a CORS “browser origin” unless another page hosted on sslip calls the API cross-origin; same-origin calls from the EC2-hosted SPA already work when that SPA is served from the same host as `/api`.

## Required secrets (summary)

| Area | Secret / variable | Purpose |
|------|-------------------|---------|
| AWS | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Terraform + API access |
| AWS | `AWS_REGION` | Region for provider, S3 backend, and `TF_VAR_aws_region` |
| Terraform | `TF_STATE_BUCKET`, optional `TF_STATE_KEY`, `TF_STATE_DYNAMODB_TABLE` | **Production only** — remote state |
| Terraform | `TF_VAR_KEY_NAME` (workflow maps to env `TF_VAR_key_name`), `TF_VAR_SSH_ALLOWED_CIDR` | EC2 key pair name; SSH ingress CIDR |
| Terraform | Optional `TF_VAR_PROJECT_NAME`, `TF_VAR_ENVIRONMENT` | Default to `cns` and `prod` when unset |
| EC2 (compose on instance) | **`POSTGRES_PASSWORD`**, **`CNS_CORS_ORIGINS`** | Required for **first** automated deploy: create **`~/cloud-networking-studio/.env`** on EC2 when the file is missing (see **EC2 bootstrap and `.env`**). Include Vercel origins and **`https://<EIP>.sslip.io`** in **`CNS_CORS_ORIGINS`** as needed. |
| EC2 | `EC2_SSH_PRIVATE_KEY` | PEM for `appleboy/ssh-action` |
| EC2 | `EC2_SSH_USER` | e.g. `ubuntu` |
| Vercel | `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` | `vercel pull` / `build` / `deploy` |

Never commit keys, `terraform.tfvars`, or tokens. Fork PRs do not receive secrets (ephemeral workflow skips them).

See **`docs/EPHEMERAL_CI_ENVIRONMENTS.md`** for ephemeral-specific behavior (PR stacks use **HTTP** `stack_base_url_sslip_http` for smoke so CI does not depend on ACME on short-lived sslip; **HTTPS** on sslip remains the production and Vercel path).
