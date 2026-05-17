# Runtime access and integration layer (Step 39A–39C)

This document describes how **Cloud Networking Studio** exposes deployed topologies as **usable runtime environments**, not only as successful “deploy” records. The control plane persists structured **runtime resources** from the Go runner (when present) and serves them through authenticated **deployment runtime** APIs and the **Runtime access** UI panel.

## Goals

- Let project members **discover how to connect** to workloads: local machine, applications, CI/CD, other Kubernetes workloads, and the CNS HTTP API.
- Keep the design **provider-agnostic** at the API level: the same response envelope works for **Docker** and **Kubernetes**, with provider-specific details carried in rows and instructions.
- **Graceful degradation**: if the runner omits `runtime_access`, deployments still succeed; the API returns an empty resource list and generic instructions.

## Data model

### Runner (`runtime_access`)

On successful deploy, the Go runner may attach **`runtime_access`** to the deployment response:

- `deployment_id`, `topology_id`, `status` (e.g. `running`)
- `runtime_provider`: `docker` or `kubernetes`
- `namespace_or_network`: Docker user-defined network name or Kubernetes namespace
- `resources[]`: typed rows (`network`, `node`, `service`, …) with optional `node_id` / `service_id`, `runtime_name`, `ports`, `internal_url`, `external_url`, `metadata`

The FastAPI control plane maps this into **`deployment_runtime_resources`** (SQLAlchemy model `DeploymentRuntimeResource`) and replaces all rows for that deployment when a new payload arrives.

### Control plane APIs

All routes require a user who can **view the deployment** (same join as other deployment reads: project membership + topology ownership).

| Method | Path | Purpose |
|--------|------|--------|
| GET | `/deployments/{id}/runtime` | Full snapshot: live inspect data + persisted access rows + **instructions** |
| GET | `/deployments/{id}/runtime/nodes` | Persisted rows with `type == "node"` |
| GET | `/deployments/{id}/runtime/services` | Persisted rows with `type == "service"` |
| GET | `/deployments/{id}/runtime/instructions` | Instructions only (no container/network noise) |
| GET | `/deployments/{id}/runtime/logs` | **Pointers** to per-node logs (`GET /nodes/{node_id}/logs`); not a full log aggregator |

### `/api` prefix and reverse proxies

Handlers are mounted at the paths in the table (**no** leading ``/api`` in the FastAPI route table). **Caddy** ``handle_path /api/*`` and the **Vite** dev proxy strip ``/api`` before forwarding, so a browser call to ``https://host/api/deployments/{id}/runtime`` becomes ``/deployments/{id}/runtime`` on the app.

When you **curl the API container directly** using the same public-style URLs (``http://127.0.0.1:8000/api/deployments/...``), **StripApiPrefixMiddleware** removes the ``/api`` prefix so those requests hit the same routes. For scripts that bypass any proxy, you may call canonical paths without ``/api``.

Deployment runtime responses merge live provider inspection with **persisted** ``deployment_runtime_resources`` rows (when the runner returned ``runtime_access``). Topology-wide inspection remains at ``GET /topologies/{id}/runtime`` (a different aggregate).

## Integration modes (instructions)

The `instructions` object on `GET .../runtime` (and the dedicated instructions route) is keyed for multiple workflows:

| Key | User-facing title | Contents |
|-----|-------------------|----------|
| `local_dev` | Connect from local machine | Example `kubectl port-forward` + `curl` when a cluster service URL exists; otherwise Docker-oriented hints |
| `app_env` | Use from app | Suggested env vars (e.g. internal URL when known) |
| `ci_cd` | Use in CI/CD | Example `curl` deploy/destroy and test invocation patterns |
| `kubernetes` | Use from Kubernetes workload | Notes plus example `config_map` labels / DNS |
| `api` | Control through API | List of relevant HTTP paths |

These titles match the product wording in the UI (“Runtime access” / “Use this deployment”) and are **not** tied to a single “app binding” workflow.

## Docker provider behavior

- **Network**: a row describes the labeled bridge network; `namespace_or_network` aligns with that network name.
- **Nodes**: container name and best-effort **internal HTTP URL** on the Docker DNS name (same user-defined bridge).
- **Services**: a logical “service” row per node mirrors connectivity metadata (ports, internal URL) for symmetry with Kubernetes.

Host port publishing and public URLs are **not** required for this foundation step; `external_url` is optional when the runner exposes it.

## Kubernetes provider behavior

- **Namespace**: derived from project/topology/deployment ids (stable CNS naming).
- **Workloads**: Deployment + Service per plan node; labels include `app=cloud-networking-studio`, `topology_id`, `deployment_id`, and `project_id` when present.
- **DNS**: internal URLs use cluster DNS: `http://{service}.{namespace}.svc.cluster.local:{port}`.

## Python executor (`RUNTIME_EXECUTOR=python`)

When provisioning runs in-process (fake or real Docker via **docker-py**), the runner does not emit `runtime_access`. The runtime APIs still respond: **empty** persisted rows, **minimal** instructions, and the usual topology/deployment inspect fields.

## Consuming topology services

1. Deploy the topology and wait for **succeeded** status.
2. Open **Runtime access** on the topology detail page (or call `GET /deployments/{id}/runtime`).
3. Use **Endpoints** and **Instructions** to pick the integration path (port-forward, in-cluster DNS, env vars, CI scripts, API calls).

## Future work (Step 39D / 39E and beyond)

- **Expose selected services**: choose which logical services appear in instructions and external routing.
- **Exec / shell**: interactive debugging from the UI or API.
- **API tokens**: scoped credentials for automation.
- **CLI**: first-class command-line client wrapping these APIs.
- **Templates**: cookie-cutter snippets for common stacks (ingress, mTLS, sidecars).

These are intentionally out of scope for 39A–39C so the registry, APIs, and UX foundation stay stable and reviewable.
