# Service exposure and external access (Step 40)

This document describes how **Cloud Networking Studio** lets project **members** and **owners** register **how a deployed service can be reached** from outside the lab network (laptop, CI, demos), without requiring a full public ingress stack in this release.

## What gets stored

When you call **Expose** on a persisted runtime **service** row (`deployment_runtime_resources` with `resource_type=service`), the control plane creates a **`deployment_service_exposures`** row:

| Field | Meaning |
|-------|---------|
| `exposure_type` | `port_forward`, `docker_host_port`, `kubernetes_service`, or `ingress_placeholder` (reserved) |
| `external_url` / `external_host` / `external_port` | Populated when Docker publishes a host port we can read from `docker inspect` |
| `status` | `active`, `expired`, `removed`, or `failed` |
| `expires_at` | Optional TTL from the expose request |
| `metadata` | Commands, notes, and “manual port-forward required” hints |

**Viewers** can list exposures and see them in **Runtime access** instructions; only **members/owners** (topology editors) may expose or unexpose.

## HTTP API

| Method | Path | Who |
|--------|------|-----|
| GET | `/deployments/{id}/runtime/exposures` | Any project member who can see the deployment |
| POST | `/deployments/{id}/runtime/services/{service_id}/expose` | Topology editor (member/owner) |
| DELETE | `/deployments/{id}/runtime/services/{service_id}/expose` | Topology editor |

Path segment **`service_id`** is either:

1. The UUID of the **`deployment_runtime_resources`** row (shown as `id` in the Services API), or  
2. The row’s **`service_id`** column (often the topology node id the runner attached to the logical service).

Optional JSON body on POST: `{ "ttl_hours": <1..720> }`.

## Docker mode

- After deploy, the **Go runner** inspects each container and records **`host_port_bindings`** in runtime metadata when `docker` published ports exist; otherwise it sets **`external_access=manual_port_forward_required`**.
- When you **Expose**, the Python control plane runs a best-effort **`docker inspect`** (when not using fake Docker) to detect published ports. If found, `exposure_type` becomes **`docker_host_port`** and `external_url` is set to `http://127.0.0.1:<port>/` (or the bound host IP).
- If nothing is published, the exposure stays **`port_forward`** with generated **commands** in `metadata` (shell hints, not an automated tunnel).

## Kubernetes mode

- Services are **ClusterIP** by default. The runner annotates runtime metadata with **`public_access=manual_port_forward_required`** and a sample **`kubectl port-forward`** command.
- Exposing a service records **`kubernetes_service`** reachability metadata and **port-forward** style commands; there is **no automatic public URL** in this step.

## UI

On **Runtime access → Services**, each row has **Expose / Unexpose**, shows **external URL** when known, otherwise **generated commands**, plus **status** and **expiration**.

Runtime **instructions** gain an **`exposed_services`** block and extra **`curl`** examples under **Connect from local machine** when URLs exist.

## Current limitations

- No managed **Ingress**, custom domains, or TLS termination in the control plane.
- No long-lived **reverse tunnel** or SaaS broker; users run `kubectl port-forward`, Docker port publishing, or their own edge stack.
- **Fake Docker** and CI without a daemon always get **manual** hints.

## Future work

- Optional **Ingress** / **Gateway API** integration per project.
- **NodePort** or **LoadBalancer** opt-in with RBAC-scoped service accounts.
- **API tokens** scoped to expose/unexpose automation.
- **CLI** helpers wrapping the same HTTP API.

See also [RUNTIME_ACCESS.md](./RUNTIME_ACCESS.md) for the broader runtime access layer (Step 39).
