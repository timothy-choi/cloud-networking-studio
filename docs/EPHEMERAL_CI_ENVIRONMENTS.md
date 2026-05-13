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

## Lifecycle

1. One **Terraform apply infrastructure** step: writes **`backend.ci.hcl`**, **`rm -rf .terraform`**, **`terraform init -input=false -reconfigure`** (with **`TF_CLI_ARGS_init=-backend-config=backend.ci.hcl`**), then **`validate`**, **`plan`**, **`apply`**, and **`terraform output`** in the **same** `run:` block.
2. **SSH**: clone repo, **`git checkout` the PR/commit SHA**, write **`.env`**, **`docker compose ... up -d --build`**.
3. **Smoke**: `scripts/prod_smoke_test.sh` with **`CNS_BASE_URL`** = **`stack_base_url_sslip`** (HTTPS, longer wait for certificate issuance).
4. **Optional heavy smoke**: **`--heavy`** (deploy/destroy topology) runs with **`continue-on-error: true`** because Docker-on-EC2 behavior can vary.
5. **`Terraform destroy infrastructure`** with **`if: always()`**: regenerate **`backend.ci.hcl`** (same state key as apply), **`rm -rf .terraform`**, **`terraform init -input=false -reconfigure`**, **`terraform destroy -auto-approve`** (same **`TF_CLI_ARGS_init`** pattern).

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
| `TF_VAR_SSH_ALLOWED_CIDR` | Security group SSH source (GitHub-hosted runners need a CIDR that includes the runner; lab accounts sometimes use `0.0.0.0/0` — understand the risk) |
| `EC2_SSH_PRIVATE_KEY` | PEM private key matching `TF_VAR_KEY_NAME` |
| `EC2_SSH_USER` | SSH login (e.g. `ubuntu`) |

**Vercel** secrets are **not** required for this workflow.

Production additionally needs optional **`TF_STATE_KEY`** (defaults to `cloud-networking-studio/prod/terraform.tfstate`) plus **Vercel** token/org/project — see **`docs/CICD_DEPLOYMENT.md`**.
