# Runtime operations (Step 41)

This document describes **logs**, **health checks**, and **traffic tests** for deployed topologies. These APIs complement [RUNTIME_ACCESS.md](./RUNTIME_ACCESS.md) (persisted `runtime_access` rows, exposure, and instructions).

## Control plane routes

All routes require authentication and project membership on the deployment’s topology.

| Method | Path | Who |
|--------|------|-----|
| GET | `/api/deployments/{deployment_id}/runtime/logs` | Viewer+ |
| GET | `/api/deployments/{deployment_id}/runtime/services/{service_id}/logs` | Viewer+ |
| POST | `/api/deployments/{deployment_id}/runtime/services/{service_id}/health-check` | Member / owner |
| POST | `/api/deployments/{deployment_id}/runtime/traffic-tests` | Member / owner |

`service_id` in the path is the **`deployment_runtime_resources.id`** UUID (the same id used for `/runtime/services/{id}/expose`).

## Response shapes

### Logs

```json
{
  "deployment_id": "…",
  "service_id": null,
  "logs": "…",
  "items": [],
  "runtime_provider": "docker"
}
```

### Health check

```json
{
  "status": "passed|failed|unsupported",
  "target": "http://127.0.0.1:80/",
  "latency_ms": 12,
  "message": "…"
}
```

### Traffic test

Request body:

```json
{
  "source_runtime_resource_id": "…",
  "target": "other-node-uuid or https://…",
  "protocol": "http|ping"
}
```

Response:

```json
{
  "status": "passed|failed|unsupported",
  "source": "…",
  "target": "…",
  "protocol": "ping",
  "output": "…",
  "latency_ms": 42
}
```

## Go runner (`RUNTIME_EXECUTOR=go`)

When the control plane delegates to the Go runner, it calls:

- `GET /deployments/{id}/runtime/logs?topology_id=&project_id=&tail=`
- `GET /deployments/{id}/runtime/services/{workload_node_id}/logs?…` — path segment is the **topology node id** used to locate the container or pod (resolved from the persisted resource row by the API).
- `POST /deployments/{id}/runtime/services/{workload_node_id}/health-check?topology_id=&project_id=`
- `POST /deployments/{id}/runtime/traffic-tests` with JSON body (`topology_id`, `deployment_id`, `source_node_id`, `target`, `protocol`, …).

Runner failures surface as **502** (bad gateway from runner) or **503** (runner unreachable).

## Docker behavior

- **Logs**: Docker engine `logs` for each labeled workload (`cns.topology_id`, `cns.node_id`) or for a single node.
- **Health**: `wget` against `http://127.0.0.1:{port}{path}` **inside** the container (in-network loopback).
- **Traffic**: `ping` / `wget` **exec** in the source container toward the target container IP, or `wget` toward an absolute `http(s)://` URL. `ping` to a URL returns `unsupported`.

## Kubernetes behavior

- **Logs**: Pod logs in the deployment namespace for each `cns.io/node-id` workload (or a single node).
- **Health**: `wget` loopback inside the pod (same pattern as Docker).
- **Traffic**: `kubectl exec`-style traffic via the client-go remote command API; URL targets use `wget` from the source pod. No temporary Job is created (keeps deploy/destroy paths simple).

## Python executor fallback

If `RUNTIME_EXECUTOR` is not `go`:

- **Logs**: Uses the existing Python runtime provider (`fetch_logs_for_node`) per topology node.
- **Health**: Best-effort HTTP GET from the **control plane** to `internal_url` when present (often **unsupported** for in-cluster DNS).
- **Traffic**: Returns **`unsupported`** with a message to enable the Go runner for in-network tests.

## Future: shell / exec (Step 41D)

Interactive shell or arbitrary exec is **not** part of Step 41. A future step can add a scoped exec API (argv allow-list, timeouts, and RBAC) without changing the routes above.

## UI

The deployment **Runtime access** panel includes **Logs**, **Health checks**, and **Traffic tests** tabs that call these APIs.
