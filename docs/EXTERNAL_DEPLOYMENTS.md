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

Supported references (dev/local):

| Reference | Resolution |
|-----------|------------|
| `dev:default` | Server env `CNS_EXTERNAL_DEPLOY_SSH_KEY_PATH` → path to PEM file |
| `env:VAR_NAME` | Server env `VAR_NAME` → path to PEM file |

Example production setup:

```bash
export CNS_EXTERNAL_DEPLOY_SSH_KEY_PATH=/run/secrets/cns-external-ssh.pem
```

Target `credentials_ref`: `dev:default` or `env:CNS_EXTERNAL_DEPLOY_SSH_KEY_PATH`

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

| Symptom | Check |
|---------|-------|
| Validate fails: missing config | Ensure `host`, `ssh_user`, `remote_workdir` in config |
| credentials_ref error | Set `CNS_EXTERNAL_DEPLOY_SSH_KEY_PATH` or `env:VAR` on API server |
| SSH connection refused | Security group / firewall, `ssh_port`, host reachable from API |
| docker compose failed | Remote user in `docker` group; compose plugin installed |
| Destroy disabled | No active external deployment for selected target |

Job logs include masked output from SSH/SCP and compose commands — never raw key material.
