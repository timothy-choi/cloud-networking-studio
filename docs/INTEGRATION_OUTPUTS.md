# Integration outputs (Step 51A)

Integration outputs help you connect a **deployed CNS topology** to your own applications, scripts, CI/CD jobs, Docker Compose stacks, and Kubernetes workloads.

Use them when you want to:

- Point a local app at a lab service URL
- Export env vars for pytest or integration tests
- Wire GitHub Actions to deploy, test, and destroy CNS labs
- Mount service URLs into your own Compose or ConfigMap

**Related (topology-scoped IaC):** Terraform, Ansible, Docker Compose, and Kubernetes exports live under `GET /api/topologies/{topology_id}/exports/*` — see [ARCHITECTURE.md](ARCHITECTURE.md) and the **IaC Export** panel on the topology page. Integration outputs here are **deployment-scoped** snippets for apps and CI.

## API

```http
GET /api/deployments/{deployment_id}/integration-outputs
Authorization: Bearer <token>
```

**Permissions:** Any project member who can **view** the deployment (viewer, member, owner). Non-members receive `404`.

### Downloadable files

| Endpoint | Description |
|----------|-------------|
| `GET .../integration-outputs/files` | JSON manifest of downloadable files |
| `GET .../integration-outputs/files/{file_name}` | Single file (`Content-Disposition: attachment`) |
| `GET .../integration-outputs/archive` | Zip of all integration files |

Allowed filenames (allowlist only — path traversal rejected):

- `cns.env`, `cns-integration.sh`, `cns_integration.py`, `cns-integration.js`, `cns-integration.ts`
- `CnsIntegration.java`, `cns_integration.go`, `cns_integration.rb`, `cns_integration.php`, `CnsIntegration.cs`
- `github-actions-cns.yml`, `docker-compose.env`, `kubernetes-configmap.yaml`

Archive download: `cns-integration-outputs.zip`

### Response overview

| Field | Description |
|-------|-------------|
| `deployment_id` | Active deployment UUID |
| `runtime_provider` | `docker` or `kubernetes` |
| `services[]` | Per-service URLs, ports, env var names, internal vs external scope |
| `outputs` | Copy-paste snippets (`env`, `curl`, `python`, `github_actions`, etc.) |

## Internal vs external endpoints

| Type | When | Use in your project |
|------|------|---------------------|
| **External** | Service exposed (host port, published route, active exposure record) | Apps on your laptop, CI runners, other hosts |
| **Internal only** | Only `internal_url` (Docker DNS / cluster DNS) | Workloads **inside** the same runtime network |

When only an internal URL exists, outputs include:

> Internal runtime URL — usable from inside the topology/runtime network only.

External URLs are **preferred** in app and CI snippets when available.

## Environment variables

Generated names are sanitized (uppercase, alphanumeric + underscore). Examples:

```env
CNS_DEPLOYMENT_ID=...
CNS_TOPOLOGY_ID=...
API_SERVICE_URL=http://127.0.0.1:18080/
REDIS_URL=redis://redis:6379
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
```

## Language snippets

The `outputs` object includes:

- `curl`, `bash`
- `python`, `javascript`, `typescript`
- `java`, `go`, `ruby`, `php`, `csharp`

Each snippet reads the recommended env var (for example `API_SERVICE_URL`) and shows a minimal HTTP request example.

## CI/CD (GitHub Actions)

`outputs.github_actions` includes:

1. Set `CNS_API` and `CNS_TOKEN`
2. Use the deployment service URL in a test step
3. Optional destroy/cleanup via the CNS API

Create a **personal API token** in CNS (`POST /api-tokens`) and store it as `CNS_TOKEN` in GitHub Secrets.

See also [CI/CD integration](./CI_CD_INTEGRATION.md).

## Docker Compose

`outputs.docker_compose_env` provides:

- An `env_file` / `environment` block for your own `docker-compose.yml`
- A companion `.env` file body you can save as `cns-deployment.env`

## Kubernetes ConfigMap

`outputs.kubernetes_configmap` is a ready-to-apply ConfigMap with service URLs and CNS metadata labels.

Mount it in your app pod:

```yaml
envFrom:
  - configMapRef:
      name: cns-deployment-outputs
```

## UI

Open a topology → deploy → **Runtime Access** → **Use outside CNS**.

Sections:

- **Environment variables**
- **App code** (language selector + bash exports)
- **CI/CD**
- **Docker Compose**
- **Kubernetes**

Each block has a **Copy** button and a **Download** button (per file). Use **Download all (.zip)** for the full archive.

## Related docs

- [Runtime Access](./RUNTIME_ACCESS.md) — live snapshot, terminal, operations
- [Service exposure](./SERVICE_EXPOSURE.md) — publish external URLs
- [Runtime usability](./RUNTIME_USABILITY.md) — viewer vs member permissions

## Topology IaC export (separate feature)

| Endpoint | Output |
|----------|--------|
| `GET .../exports/preview` | Validation warnings + file list |
| `GET .../exports/terraform` | Terraform bundle |
| `GET .../exports/ansible` | Ansible bundle |
| `GET .../exports/docker-compose` | Compose file |
| `GET .../exports/kubernetes` | Kubernetes manifests |
| `GET .../exports/archive` | Zip of all exports |

These are **generated artifacts** from topology intent — useful for demos and handoff, not a managed Terraform/Ansible apply pipeline.
