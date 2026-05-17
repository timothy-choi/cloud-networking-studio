# Go runtime runner (`cns-runner`)

## Why it exists

Cloud Networking Studio started with a **FastAPI control plane** and a **Python Docker runtime** inside the API process. That works well for Docker Compose today, but it couples the control plane to Docker SDK usage and long-running orchestration work.

The **Go runner** (`runner/`, binary `cns-runner`) is an **optional** HTTP service that sits between FastAPI and the engine:

- **FastAPI** — auth, projects, persistence, deployment records, traffic-test records, public HTTP API.
- **Go runner** — deploy/destroy/logs/traffic-test execution against Docker **now**, with room for a **Kubernetes** implementation later without growing the Python process.

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
                                              └─► Docker Engine API
```

When `RUNTIME_EXECUTOR=go` and `runtime_target` is `docker`, the API uses **`GoHybridDockerRuntimeProvider`**: deploy, destroy, node logs, and traffic tests are sent to the runner; **inspect**, **stats**, **reconcile**, **exec** (except traffic), and lifecycle helpers still use **docker-py** in the backend for consistent behaviour until the Go surface fully replaces those paths.

## Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `RUNTIME_EXECUTOR` | `python` | `python` — all Docker work in FastAPI (legacy). `go` — delegate mutating Docker work to the runner. |
| `GO_RUNNER_URL` | `http://runner:8090` | Base URL of `cns-runner` (Compose service name `runner` on the `cns` network). |
| `GO_RUNNER_TIMEOUT_SECONDS` | `600` | HTTP client timeout for runner calls. |
| `CNS_USE_FAKE_DOCKER` | unset | When `1`/`true`/`yes`, the stack uses the fake provider and **never** calls the Go runner, even if `RUNTIME_EXECUTOR=go`. |

The runner listens on **`8090`** by default, or `RUNNER_LISTEN_ADDR` inside the runner container.

## Docker Compose

`docker-compose.prod.yml` defines a **`runner`** service (internal port `8090`, Docker socket mounted). The **backend** declares `depends_on: runner` with `condition: service_started` so the runner container exists before the API starts. With `RUNTIME_EXECUTOR=python`, the backend does not call the runner unless you switch executor.

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

The Go Docker path implements **non-segmented** topologies (single CNS bridge). **Segmented multinet** deployments still require `RUNTIME_EXECUTOR=python` until the Go provider gains parity.

## Future: Kubernetes provider

The runner package layout (`internal/runtime/docker/`, future `internal/runtime/kubernetes/`) is meant to grow a **second adapter** behind the same HTTP contract so FastAPI can keep one integration (`go_runner_client.py`) while the active engine switches from Docker to Kubernetes per topology or global config.
