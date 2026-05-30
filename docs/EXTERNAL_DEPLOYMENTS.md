# External Deployments (Step 57)

Cloud Networking Studio can deploy topology exports to **external targets** outside the built-in CNS Docker/Kubernetes runtime. Step 57B implements real **remote Docker Compose** execution for `remote_docker` targets.

## Overview

| Target type     | validate | plan | apply | destroy |
|-----------------|----------|------|-------|---------|
| `remote_docker` | yes      | yes  | yes   | yes     |
| `terraform`     | stub     | stub | no    | no      |
| `ansible`       | stub     | stub | no    | no      |
| `kubernetes`    | stub     | stub | no    | no      |

External deployment jobs are **separate** from internal CNS runtime deploys (`/deployments`). They do not modify the CNS-managed runtime stack.

## User flow (remote_docker)

1. **Create target** — Project → Topology → External Deployments → New target (`remote_docker`).
2. **Validate** — SSH to the host; verify `docker --version` and `docker compose version`.
3. **Plan** — Generate Docker Compose from the topology effective config; show a plan summary (no remote changes).
4. **Apply** — SCP compose files to the remote host and run `docker compose up -d`.
5. **View status** — Jobs tab shows logs; Deployments tab shows active/destroyed records.
6. **Destroy** — Run `docker compose down --remove-orphans` on the remote host.

## Remote Docker target config

```json
{
  "host": "203.0.113.10",
  "ssh_user": "ubuntu",
  "ssh_port": 22,
  "remote_workdir": "/opt/cns-external-deployments",
  "supports_compose": true
}
```

Required fields: `host`, `ssh_user`, `remote_workdir`.

Remote layout after apply:

```
{remote_workdir}/cns-{topology_id[:8]}/{job_id[:8]}/
  docker-compose.cns.yml
  .env.cns              (if topology nodes define env vars)
  metadata.json
```

Compose project name: `cns-ext-{job_id[:8]}`

## credentials_ref

SSH private keys are **never** stored in `config_json` or the database.

Supported references:

| Reference | Resolution |
|-----------|------------|
| `env:CNS_REMOTE_DOCKER_SSH_KEY_PATH` | Server env → path to PEM file (recommended for staging/prod) |
| `env:VAR_NAME` | Any server env var → path to PEM file |
| `dev:default` | `CNS_REMOTE_DOCKER_SSH_KEY_PATH` or `CNS_EXTERNAL_DEPLOY_SSH_KEY_PATH` |

### Staging / production credential setup

The backend container includes **`openssh-client`** (`ssh` and `scp` binaries) and mounts host secrets read-only:

```yaml
# docker-compose.prod.yml (backend service)
environment:
  CNS_REMOTE_DOCKER_SSH_KEY_PATH: ${CNS_REMOTE_DOCKER_SSH_KEY_PATH:-}
volumes:
  - /opt/cns/secrets:/opt/cns/secrets:ro
```

**One-time on the CNS host (staging EC2 or production):**

```bash
sudo install -d -m 0750 /opt/cns/secrets
sudo install -m 0600 /path/to/private-key.pem /opt/cns/secrets/gcp-remote-docker-key
sudo chown ubuntu:ubuntu /opt/cns/secrets/gcp-remote-docker-key
```

**Staging deploy** writes `.env.staging` on each deploy with a non-empty path:

```bash
CNS_REMOTE_DOCKER_SSH_KEY_PATH=/opt/cns/secrets/gcp-remote-docker-key
```

Resolution order in `scripts/staging_deploy_remote.sh`:

1. GitHub variable/secret `CNS_REMOTE_DOCKER_SSH_KEY_PATH` (if set)
2. Existing non-empty value in `.env.staging` (never overwritten with blank)
3. Default `/opt/cns/secrets/gcp-remote-docker-key`

Set repository variable `CNS_REMOTE_DOCKER_SSH_KEY_PATH` to override the default path.

Target `credentials_ref`: `env:CNS_REMOTE_DOCKER_SSH_KEY_PATH`

### Add public key to remote Docker VM

On the **target** host (e.g. GCP VM), install the **public** key for the private key mounted in CNS:

```bash
# On your laptop — copy public key material (never commit private keys)
ssh-copy-id -i /path/to/key.pub ubuntu@YOUR_GCP_VM_IP

# Or manually on the target VM:
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo 'ssh-ed25519 AAAA...your-public-key...' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Ensure Docker and Compose v2 are installed and the SSH user can run `docker compose` without a TTY.

## Remote host setup

1. Ubuntu/Debian VM or cloud instance with Docker Engine and Docker Compose v2 plugin.
2. SSH access for the configured user (key-based auth recommended).
3. User in the `docker` group (or root) so `docker compose` works non-interactively.
4. Writable `remote_workdir` (default `/opt/cns-external-deployments`).

Example bootstrap:

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin
sudo usermod -aG docker ubuntu
sudo mkdir -p /opt/cns-external-deployments
sudo chown ubuntu:ubuntu /opt/cns-external-deployments
```

Ensure the CNS API server can reach the host on `ssh_port` (default 22).

## Security warnings

- **Do not** put private keys, tokens, or passwords in target `config_json`.
- **Do not** log or return secret values in job logs, API errors, or audit metadata.
- Restrict SSH keys to the minimum remote permissions needed.
- External apply runs arbitrary container images from the topology export — treat remote hosts as untrusted execution environments unless you control image sources.
- Use firewall rules so only the CNS API server (or your CI runner) can SSH to deployment hosts.

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/topologies/{id}/external-deployments` | List deployment records |
| GET | `/topologies/{id}/external-deployment-jobs` | List jobs |
| POST | `/topologies/{id}/external-deployment-jobs` | Create and run job (`validate`/`plan`/`apply`/`destroy`) |
| GET | `/external-deployment-jobs/{id}` | Job detail |
| GET | `/external-deployment-jobs/{id}/logs` | Job logs |

Job statuses: `queued` → `running` → `succeeded` | `failed`.

## Audit events

- `external_deployment_job.created`
- `external_deployment_job.validate`
- `external_deployment_job.plan`
- `external_deployment_job.apply`
- `external_deployment_job.destroy`

Metadata is scrubbed of secrets before persistence.

## Internal vs external deploy

| | Internal CNS deploy | External deploy |
|--|---------------------|-----------------|
| Runtime | CNS Docker/K8s executor | User's remote Docker host |
| Scope | Topology runtime lab | Exported compose stack |
| API | `/deployments` | `/external-deployment-jobs` |
| Destroy | CNS teardown | Remote `docker compose down` |

Both can coexist; external deploy does not stop or replace internal runtime deployments.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `credentials_ref env:CNS_REMOTE_DOCKER_SSH_KEY_PATH is not set on the server` | Env var blank in backend container | Set in `.env.staging` / `.env`; redeploy backend; verify `printenv CNS_REMOTE_DOCKER_SSH_KEY_PATH` |
| `SSH key path is configured but not readable by backend container` | Key missing or wrong permissions | Install key at configured path; mode `0600`; ensure `/opt/cns/secrets` is mounted |
| `SSH/SCP client is missing from backend container` | Old backend image without `openssh-client` | Rebuild backend image (`docker compose up -d --build backend`) |
| `SSH permission denied. Check public key is installed for ssh_user on target host.` | Public key not in target `authorized_keys` | Run `ssh-copy-id` or add pubkey to target VM |
| Validate fails: missing config | Incomplete target config | Ensure `host`, `ssh_user`, `remote_workdir` |
| SSH connection refused | Network/firewall | Security group, `ssh_port`, routing from CNS host to target |
| docker compose failed on remote | Docker not installed or user lacks docker group | Install Docker Compose plugin; add user to `docker` group |
| Destroy disabled | No active external deployment | Apply first, or select correct target |

### Staging deploy verification (safe checks)

After **Deploy staging**, the remote script prints (no key contents):

```bash
grep CNS_REMOTE_DOCKER_SSH_KEY_PATH .env.staging
docker compose exec backend printenv CNS_REMOTE_DOCKER_SSH_KEY_PATH
docker compose exec backend test -r "$CNS_REMOTE_DOCKER_SSH_KEY_PATH"
docker compose exec backend command -v ssh
docker compose exec backend command -v scp
```

Job logs include masked SSH/SCP output — never raw private key material.
