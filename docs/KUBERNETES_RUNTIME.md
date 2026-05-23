# Kubernetes runtime (Go runner)

This document describes the **optional** Kubernetes execution path in **`cns-runner`**. **Docker remains the production default** (`RUNTIME_PROVIDER=docker`). Nothing here is required for normal Compose or production EC2 stacks that use Docker only.

## Why production defaults to Docker

- Production EC2 deploy workflow (`.github/workflows/deploy-production.yml`) sets `RUNTIME_EXECUTOR=go`, `RUNTIME_PROVIDER=docker`, and `GO_RUNNER_URL=http://runner:8090`.
- Docker socket access from the runner is stable on a single host and does not require cluster credentials.
- Local **kind** kubeconfigs often reference `host.docker.internal`, which is **not reliable on Linux EC2** and must never be used silently in production.

Use Kubernetes when you explicitly operate a cluster (k3s on EC2, EKS, in-cluster runner) and mount a production-grade kubeconfig.

## Architecture

```text
FastAPI (RUNTIME_EXECUTOR=go)
        │
        ▼ HTTP (same contract as Docker)
   cns-runner
        │
        ├─ RUNTIME_PROVIDER=docker ──► Docker Engine API   (default / production)
        │
        └─ RUNTIME_PROVIDER=kubernetes ──► Kubernetes API (advanced / optional)
```

When a topology uses `runtime_target=kubernetes` and the backend uses `RUNTIME_EXECUTOR=go`, deploy/destroy/logs delegate to the Go runner via **`GoHybridKubernetesRuntimeProvider`**.

## Environment variables

| Variable | Where | Default | Meaning |
|----------|-------|---------|---------|
| `RUNTIME_EXECUTOR` | Backend | `go` in prod compose | Set **`go`** to delegate mutating work to the runner. |
| `GO_RUNNER_URL` | Backend | `http://runner:8090` | Runner base URL. |
| `RUNTIME_PROVIDER` | Runner | **`docker`** | **`docker`** or **`kubernetes`**. Unknown values fall back to **`docker`**. |
| `KUBECONFIG` | Runner | — | Path to kubeconfig **inside** the runner container (only when using Kubernetes). |
| `CNS_ENVIRONMENT` | Backend/runner | `production` in prod | When `production`, local kind/minikube contexts are **rejected** by the runner. |

## Local cluster (kind / minikube)

1. Create a cluster and verify `kubectl get ns` on the host.
2. **Do not** commit kubeconfig files — add them to `.gitignore` (`.kubeconfig.cns` is ignored by default).
3. Enable Kubernetes on the runner with the overlay:

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.k8s-runtime.yml up -d
export CNS_KUBECONFIG_HOST_PATH=/path/to/your/kubeconfig
```

4. When the runner runs **inside Docker**, ensure the kubeconfig `server:` URL is reachable from the runner network (not `host.docker.internal` on Linux unless you know it resolves).

### Troubleshooting `host.docker.internal` / kind

| Symptom | Cause | Fix |
|---------|-------|-----|
| Runner `kubernetes_reachable=false`, message mentions unreachable API | kind API bound to host-only address | Use kind extraPortMappings or run runner on host with `GO_RUNNER_URL` pointing from backend |
| Production deploy accidentally uses kind | `.kubeconfig.cns` mounted with local context | Remove kubeconfig mount from prod; use Docker provider defaults |
| `/runtime/status` degraded, `kubernetes_init_error` set | Missing/invalid kubeconfig or blocked local context | Fix kubeconfig path; use overlay only for dev |

## Production options

### k3s on EC2

- Install k3s on the same or a peer EC2 instance.
- Copy kubeconfig to the runner host; set `CNS_KUBECONFIG_HOST_PATH` in the k8s overlay.
- Scope RBAC: namespace create/delete, Deployments, Services, ConfigMaps, Pods/exec — **not** cluster-admin unless required.

### Amazon EKS

- Use `aws eks update-kubeconfig` on the deploy host.
- Mount resulting kubeconfig into the runner via `docker-compose.k8s-runtime.yml`.
- Prefer IRSA / scoped IAM roles for the runner ServiceAccount when running in-cluster.

## Deployment mapping

For each deployment the runner:

1. Creates namespace **`cns-deploy-{first 8 hex of deployment UUID}`** (RFC 1123).
2. Writes ConfigMap `cns-topology-metadata` with deployment JSON.
3. For each node: Deployment + Service from final node config (image, command, env, ports, labels, optional `kubernetes_service_type`).
4. Default Service type: **ClusterIP** (internal DNS `service.namespace.svc.cluster.local`).
5. Optional **NodePort** when node config sets `kubernetes_service_type: NodePort`.
6. Applies default CPU/memory requests/limits (50m/64Mi request, 500m/512Mi limit).
7. Persists runtime resources (pod/deployment name, service, namespace, DNS, exposure mode, pod IP when available).

## Destroy

Deletes the deployment namespace (idempotent if already gone).

## Runtime status (`GET /runtime/status`)

Reports:

- `runtime_provider`, `docker_reachable`, `kubernetes_reachable`
- `current_context`, `kubeconfig_source`
- `kubernetes_init_error` when kubeconfig is missing, unreachable, or blocked in production
- `runner_reachable` (from backend merge when `RUNTIME_EXECUTOR=go`)

## Health checks and traffic

Protocol-aware checks run inside the cluster via pod exec (runtime / TCP / HTTP / command). Missing tools return **`unsupported`** with a clear message — CNS does not install tools into user images.

## Service exposure

- **ClusterIP (default):** internal-only; UI shows `exposure_mode=clusterip`.
- **NodePort:** set `kubernetes_service_type: NodePort` on the node; UI shows `exposure_mode=nodeport`.
- **Ingress:** documented future work; use kubectl/Ingress controller manually today.

## Safe exec and terminal

- Safe exec uses Kubernetes exec via the Go runner.
- Terminal sessions prefer shell fallback: `/bin/sh`, `sh`, `/bin/bash`, `bash`.
- If no shell exists in the image, the session returns a readable error — use Safe exec or kubectl.

## RBAC (recommended minimum)

Grant the runner identity:

- `namespaces` create/get/delete
- `deployments`, `services`, `configmaps` CRUD in lab namespaces
- `pods` get/list/delete, `pods/exec` create

Do **not** document or require cluster-admin for production labs.

## Known limitations

- Segmented multinet topologies are rejected.
- Control-plane inspect/reconcile/stats still target Docker in hybrid mode.
- Ingress automation is not implemented.
- Interactive terminal attach for Kubernetes is evolving; kubectl exec remains the fallback.

## Tests

- Go: `runner/internal/runtime/kubernetes/*_test.go`
- Python: `backend/tests/test_kubernetes_runtime.py`
- Docker regression: existing deploy/destroy/runtime tests unchanged when `runtime_target=docker`.
