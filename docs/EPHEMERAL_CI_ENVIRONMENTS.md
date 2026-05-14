# Ephemeral CI environments (PR Terraform)

The workflow **`.github/workflows/ephemeral-infra-smoke.yml`** provisions a **short-lived** copy of the Terraform stack (VPC, EC2, EIP), deploys **`docker-compose.prod.yml` + `docker-compose.sslip.yml`**, runs **smoke tests** against **`https://<EIP>.sslip.io`**, then **always** runs **`terraform destroy`** so the VPC and instance are torn down.

## How it differs from production

| | Production (`deploy-production.yml`) | Ephemeral PR workflow |
|--|----------------------------------------|------------------------|
| Trigger | `push` to `main`, `workflow_dispatch` | `pull_request`, `workflow_dispatch` |
| Terraform state | **S3** (required via `TF_STATE_BUCKET`) | **S3** with key `cloud-networking-studio/ephemeral/<run_id>/terraform.tfstate` |
| `terraform destroy` | **Never** (by design) | **`always()`** after tests |
| EC2 `.env` | Maintained on the instance | Generated on the fly (random Postgres password) |
| Compose directory | `~/cloud-networking-studio` | `~/cloud-networking-studio-ephemeral` (fresh clone) |
| SSH ingress (port 22) | Secret **`TF_VAR_SSH_ALLOWED_CIDR`** (e.g. **`MY_IP/32`**) | Workflow sets **`TF_VAR_ssh_allowed_cidr` = `0.0.0.0/0`** for GitHub-hosted runners |

## SSH from GitHub Actions vs your laptop

- **Local / manual Terraform or SSH:** set **`ssh_allowed_cidr`** in **`terraform.tfvars`** to **your public IPv4 `/32`** (e.g. `203.0.113.10/32`). That maps to **`var.ssh_allowed_cidr`** on the instance security group (port 22 only).
- **Ephemeral workflow (`.github/workflows/ephemeral-infra-smoke.yml`):** sets **`TF_VAR_ssh_allowed_cidr` to `0.0.0.0/0`** so **GitHub-hosted runners** can reach port 22 (runner egress IPs are not static). This is **broad exposure** while the instance exists; prefer **SSM Session Manager** later if you want to avoid open SSH from the Internet.
- **Production deploy workflow** still uses your repository secret **`TF_VAR_SSH_ALLOWED_CIDR`** (typically **`MY_IP/32`**). If Actions must SSH to prod EC2, that secret must include runner IPs or a bastion pattern — otherwise use the same **`0.0.0.0/0`** tradeoff only if you accept it.

After **`terraform apply`**, the workflow **prints Terraform outputs**, **`public_ip`**, and **security group / subnet / VPC IDs**, then **waits until TCP port 22** is reachable before **`appleboy/ssh-action`**.

## Lifecycle

1. One **Terraform apply infrastructure** step: writes **`backend.ci.hcl`**, **`rm -rf .terraform`**, **`terraform init -input=false -reconfigure`** (with **`TF_CLI_ARGS_init=-backend-config=backend.ci.hcl`**), then **`validate`**, **`plan`**, **`apply`**, and **`terraform output`** in the **same** `run:` block. **SSH ingress is `0.0.0.0/0`** for this job only (see above).
2. **Debug (pre-SSH):** print **`terraform output`**, **`public_ip`**, **`security_group_id`**, **`subnet_id`**, **`vpc_id`**.
3. **Wait for SSH:** poll until **TCP port 22** on **`public_ip`** accepts connections (up to ~5 minutes).
4. **SSH** (`appleboy/ssh-action`): clone the repo, then for **`pull_request`** fetch **`refs/pull/<N>/head`** into a local branch and checkout the **PR head SHA** (avoids the PR **merge** commit `github.sha`, which is not always fetchable on EC2). For **`workflow_dispatch`**, checkout **`github.sha`**. Prints **`git rev-parse HEAD`** and **`git status --short`**, then writes **`.env`** and runs **`docker compose ... up`**.
5. **Smoke**: `scripts/prod_smoke_test.sh` with **`CNS_BASE_URL`** = **`stack_base_url_sslip`** (HTTPS, longer wait for certificate issuance).
6. **Optional heavy smoke**: **`--heavy`** (deploy/destroy topology) runs with **`continue-on-error: true`** because Docker-on-EC2 behavior can vary.
7. **`Terraform destroy infrastructure`** with **`if: always()`**: regenerate **`backend.ci.hcl`** (same state key as apply), **`rm -rf .terraform`**, **`terraform init -input=false -reconfigure`**, **`terraform destroy -auto-approve`** (same **`TF_CLI_ARGS_init`** pattern; **`TF_VAR_ssh_allowed_cidr`** remains **`0.0.0.0/0`** so destroy matches the applied security group).

`hashicorp/setup-terraform` installs the CLI with **`terraform_wrapper: false`** so Terraform is not wrapped between steps.

If **destroy** fails (API rate limit, transient AWS error), resources may linger — re-run the workflow or clean up manually in the AWS console.

## Fork pull requests

Jobs are **skipped** when `github.event.pull_request.head.repo.full_name != github.repository` so untrusted code cannot access your repository secrets.

## Cost warning

Each run creates an **EC2 instance**, **Elastic IP**, and **VPC** resources for a few minutes. Frequent PRs **incur real AWS charges**. Consider:

- Running only on **`workflow_dispatch`** for manual validation, or  
- Narrowing **`pull_request`** branches / paths in the workflow if you fork this pattern.

## Cleanup guarantees

The **`always()`** destroy step is the primary guarantee. It runs in the **same job** as **`apply`** and re-initializes the **same S3 state key** (`cloud-networking-studio/ephemeral/<run_id>/terraform.tfstate`) before **`terraform destroy`**, so teardown targets the stack created in that workflow run.

## Secrets (GitHub)

Repository secrets are **case-sensitive**. The workflows map **`TF_VAR_KEY_NAME`** (secret) to the environment variable **`TF_VAR_key_name`** for Terraform.

| Secret | Purpose |
|--------|---------|
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` | Terraform AWS provider |
| `TF_STATE_BUCKET` | S3 bucket for Terraform state (same as production; ephemeral uses a per-run key) |
| Optional `TF_STATE_DYNAMODB_TABLE` | State locking (same pattern as production) |
| `TF_VAR_KEY_NAME` | Existing EC2 key pair name in the target region |
| `EC2_SSH_PRIVATE_KEY` | PEM private key matching `TF_VAR_KEY_NAME` |
| `EC2_SSH_USER` | SSH login (e.g. `ubuntu`) |

**Vercel** secrets are **not** required for this workflow.

Production additionally needs optional **`TF_STATE_KEY`** (defaults to `cloud-networking-studio/prod/terraform.tfstate`) plus **Vercel** token/org/project — see **`docs/CICD_DEPLOYMENT.md`**.
