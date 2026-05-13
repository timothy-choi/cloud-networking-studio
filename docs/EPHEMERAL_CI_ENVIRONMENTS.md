# Ephemeral CI environments (PR Terraform)

The workflow **`.github/workflows/ephemeral-infra-smoke.yml`** provisions a **short-lived** copy of the Terraform stack (VPC, EC2, EIP), deploys **`docker-compose.prod.yml` + `docker-compose.sslip.yml`**, runs **smoke tests** against **`https://<EIP>.sslip.io`**, then **always** runs **`terraform destroy`** so the VPC and instance are torn down.

## How it differs from production

| | Production (`deploy-production.yml`) | Ephemeral PR workflow |
|--|----------------------------------------|------------------------|
| Trigger | `push` to `main`, `workflow_dispatch` | `pull_request`, `workflow_dispatch` |
| Terraform state | **S3** (required via `TF_STATE_BUCKET`) | **Local** on the runner (`-backend=false`) |
| `terraform destroy` | **Never** (by design) | **`always()`** after tests |
| EC2 `.env` | Maintained on the instance | Generated on the fly (random Postgres password) |
| Compose directory | `~/cloud-networking-studio` | `~/cloud-networking-studio-ephemeral` (fresh clone) |

## Lifecycle

1. **`terraform init -backend=false`** — state file lives only for this job.
2. **`terraform validate`** / **`apply -auto-approve`** — unique `TF_VAR_environment=ephemeral-<run_id>` so resource names do not collide with prod.
3. **SSH**: clone repo, **`git checkout` the PR/commit SHA**, write **`.env`**, **`docker compose ... up -d --build`**.
4. **Smoke**: `scripts/prod_smoke_test.sh` with **`CNS_BASE_URL`** = **`stack_base_url_sslip`** (HTTPS, longer wait for certificate issuance).
5. **Optional heavy smoke**: **`--heavy`** (deploy/destroy topology) runs with **`continue-on-error: true`** because Docker-on-EC2 behavior can vary.
6. **`terraform destroy -auto-approve`** in a step with **`if: always()`** so teardown runs even when smoke fails.

If **destroy** fails (API rate limit, transient AWS error), resources may linger — re-run the workflow or clean up manually in the AWS console.

## Fork pull requests

Jobs are **skipped** when `github.event.pull_request.head.repo.full_name != github.repository` so untrusted code cannot access your repository secrets.

## Cost warning

Each run creates an **EC2 instance**, **Elastic IP**, and **VPC** resources for a few minutes. Frequent PRs **incur real AWS charges**. Consider:

- Running only on **`workflow_dispatch`** for manual validation, or  
- Narrowing **`pull_request`** branches / paths in the workflow if you fork this pattern.

## Cleanup guarantees

The **`always()`** destroy step is the primary guarantee. It executes in the **same job** as **`apply`**, reusing the local Terraform state produced by **`init`**. Do **not** split apply and destroy across jobs without passing state artifacts, or destroy will not match the created workspace.

## Secrets (GitHub)

Repository secrets are **case-sensitive**. The workflows map **`TF_VAR_KEY_NAME`** (secret) to the environment variable **`TF_VAR_key_name`** for Terraform.

| Secret | Purpose |
|--------|---------|
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` | Terraform AWS provider |
| `TF_VAR_KEY_NAME` | Existing EC2 key pair name in the target region |
| `TF_VAR_SSH_ALLOWED_CIDR` | Security group SSH source (GitHub-hosted runners need a CIDR that includes the runner; lab accounts sometimes use `0.0.0.0/0` — understand the risk) |
| `EC2_SSH_PRIVATE_KEY` | PEM private key matching `TF_VAR_KEY_NAME` |
| `EC2_SSH_USER` | SSH login (e.g. `ubuntu`) |

**Vercel** secrets are **not** required for this workflow.

Production additionally needs **`TF_STATE_BUCKET`** (and optional state key / lock table) plus **Vercel** token/org/project — see **`docs/CICD_DEPLOYMENT.md`**.
