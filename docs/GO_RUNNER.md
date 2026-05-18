# Go runtime runner (`cns-runner`)

## Why it exists

Cloud Networking Studio started with a **FastAPI control plane** and a **Python Docker runtime** inside the API process. That works well for Docker Compose today, but it couples the control plane to Docker SDK usage and long-running orchestration work.

The **Go runner** (`runner/`, binary `cns-runner`) is an **optional** HTTP service that sits between FastAPI and the engine:

- **FastAPI** — auth, projects, persistence, deployment records, traffic-test records, public HTTP API.
- **Go runner** — deploy/destroy/logs/traffic-test execution against **Docker** (default) or **Kubernetes** when `RUNTIME_PROVIDER` is set, without growing the Python process.

The **Python Docker provider remains** the default (`RUNTIME_EXECUTOR=python`) so existing behaviour, tests, and CI are unchanged.

## Architecture

```text
Browser / API clients
        │
        ▼
   FastAPI (control plane)
        │
        ├─ RUNTIME_EXECUTOR=python ──► docker-py (in-process)
        │
        └─ RUNTIME_EXECUTOR=go ──────► HTTP ──► cns-runner (Go)
                                              │
                                              ├─► RUNTIME_PROVIDER=docker ──► Docker Engine API
                                              │
                                              └─► RUNTIME_PROVIDER=kubernetes ──► Kubernetes API (local kubeconfig / in-cluster)
```

When `RUNTIME_EXECUTOR=go` and `runtime_target` is `docker`, the API uses **`GoHybridDockerRuntimeProvider`**: deploy, destroy, node logs, and traffic tests are sent to the runner; **inspect**, **stats**, **reconcile**, **exec** (except traffic), and lifecycle helpers still use **docker-py** in the backend for consistent behaviour until the Go surface fully replaces those paths. With **`RUNTIME_PROVIDER=kubernetes`** on the runner, those mutating calls target the cluster instead of Docker while the hybrid provider still uses docker-py for read-only inspection (see [Kubernetes runtime](KUBERNETES_RUNTIME.md)).

## Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `RUNTIME_EXECUTOR` | `python` | `python` — all Docker work in FastAPI (legacy). `go` — delegate mutating Docker work to the runner. **The API reads `RUNTIME_EXECUTOR` from the process environment first** (what Docker Compose injects), then falls back to settings so Compose env always wins over a stale `.env` baked into cwd. |
| `GO_RUNNER_URL` | `http://runner:8090` | Base URL of `cns-runner` (Compose service name `runner` on the `cns` network). |
| `GO_RUNNER_TIMEOUT_SECONDS` | `600` | HTTP client timeout for runner calls. |
| `CNS_USE_FAKE_DOCKER` | unset | When `1`/`true`/`yes`, the stack uses the fake provider and **never** calls the Go runner, even if `RUNTIME_EXECUTOR=go`. |

**Runner container** (process env read by `cns-runner`, e.g. in `docker-compose.prod.yml`):

| Variable | Default | Meaning |
|----------|---------|---------|
| `RUNTIME_PROVIDER` | `docker` | `docker` or `kubernetes` (`k8s` accepted). Selects which engine handles `POST /deployments`, `DELETE /deployments/{id}`, logs, and traffic tests. |
| `KUBECONFIG` | (default rules) | When using Kubernetes, path to kubeconfig inside the runner container (mount from host for kind/minikube). |
| `RUNNER_LISTEN_ADDR` | `:8090` | Listen address for the HTTP API. |

### Control plane status API

- **`GET /runtime/status`** (also **`GET /api/runtime/status`** behind Caddy) — public probe, no auth.
  - **`RUNTIME_EXECUTOR=python`** — returns JSON including `backend_status`, `runtime_executor`, `docker_reachable`, and related probe fields.
  - **`RUNTIME_EXECUTOR=go`** — merges JSON from **`GET {GO_RUNNER_URL}/runtime/status`**. If the runner is unreachable, the API still returns **HTTP 200** with `status: degraded`, `runner_reachable: false`, and `message` describing the failure (so dashboards can render without treating the probe as a hard outage). When the runner uses Kubernetes, expect **`kubernetes_reachable`**, **`current_context`**, and **`runtime_provider`** reflecting the runner configuration (see [Kubernetes runtime](KUBERNETES_RUNTIME.md)).

## Docker Compose

`docker-compose.prod.yml` defines a **`runner`** service (internal port `8090`, Docker socket mounted). The **backend** declares `depends_on: runner` with `condition: service_started` so the runner container exists before the API starts. With `RUNTIME_EXECUTOR=python`, the backend does not call the runner unless you switch executor. **`RUNTIME_PROVIDER`** defaults to **`docker`** on the runner; set **`kubernetes`** only when the runner container has a working kubeconfig (see [Kubernetes runtime](KUBERNETES_RUNTIME.md)).

## Local development

### Python only (default)

```bash
cd backend
export CNS_USE_FAKE_DOCKER=1   # optional; tests use this
uvicorn app.main:app --reload
```

### Go runner from source

```bash
cd runner
go test ./...
go run ./cmd/runner
# listens on :8090 unless RUNNER_LISTEN_ADDR is set
```

Point the API at it:

```bash
export RUNTIME_EXECUTOR=go
export GO_RUNNER_URL=http://127.0.0.1:8090
unset CNS_USE_FAKE_DOCKER   # real Docker required for hybrid + runner
```

### Limitations today

The Go Docker path implements **non-segmented** topologies (single CNS bridge). **Segmented multinet** deployments still require `RUNTIME_EXECUTOR=python` until the Go provider gains parity. The Go Kubernetes path does not support segmented multinet yet either.

## Kubernetes runtime

See **[docs/KUBERNETES_RUNTIME.md](KUBERNETES_RUNTIME.md)** for architecture, local kind/minikube setup, namespace mapping, and limitations.
