# Kubernetes runtime (Go runner)

This document describes the **optional** Kubernetes execution path in **`cns-runner`**. Docker remains the default (`RUNTIME_PROVIDER=docker`). Nothing here is required for normal Compose or production stacks that use Docker only.

## Architecture

```text
FastAPI (RUNTIME_EXECUTOR=go)
        │
        ▼ HTTP (same contract as Docker)
   cns-runner
        │
        ├─ RUNTIME_PROVIDER=docker ──► Docker Engine API
        │
        └─ RUNTIME_PROVIDER=kubernetes ──► Kubernetes API (client-go)
```

The control plane still uses **`go_runner_client.py`**. Runner routes (`POST /deployments`, `DELETE /deployments/{id}`, logs, traffic tests, `GET /runtime/status`) branch on **`RUNTIME_PROVIDER`** inside the runner. FastAPI does not need a second client.

## Environment variables

| Variable | Where | Default | Meaning |
|----------|-------|---------|---------|
| `RUNTIME_EXECUTOR` | Backend | `python` | Set **`go`** to delegate mutating work to the runner. |
| `GO_RUNNER_URL` | Backend | `http://runner:8090` | Runner base URL. |
| `RUNTIME_PROVIDER` | Runner | `docker` | **`docker`** or **`kubernetes`** (alias **`k8s`**). Unknown values fall back to **`docker`**. |
| `KUBECONFIG` | Runner | kubeconfig default rules | Path to kubeconfig **inside the runner container** when not using in-cluster config. |
| `RUNNER_LISTEN_ADDR` | Runner | `:8090` | HTTP listen address. |

## Local cluster (kind / minikube)

1. Create a cluster on the host (for example **kind** or **minikube**) and verify `kubectl get ns` works on the host.
2. When running the runner **inside Docker Compose**, the API server address in your host kubeconfig is often **not** reachable from inside another container. Typical approaches:
   - Mount kubeconfig and set **`KUBECONFIG`** to a copy whose `server:` URL is reachable from the runner network (for example the host gateway or kind’s extra port mappings).
   - Run **`cns-runner` on the host** (`go run ./cmd/runner`) with `RUNTIME_PROVIDER=kubernetes` and point **`GO_RUNNER_URL`** at `http://host.docker.internal:8090` from the backend container (platform-dependent).
3. Grant RBAC in the cluster for the runner identity (ServiceAccount when in-cluster, or kubeconfig user) to create/delete namespaces, Deployments, Services, and ConfigMaps in the target namespaces.

Details vary by tool; start from your vendor’s “access API from a container” guidance.

## How deployments map to Kubernetes

For each deployment request the runner:

1. Computes a **namespace** (RFC 1123, max 63 characters):
   - With **`project_id`** on the request: `cns-p-{first 8 hex of project UUID}-d-{first 8 hex of deployment UUID}`.
   - Without project: `cns-t-{first 8 hex of topology UUID}-d-{first 8 hex of deployment UUID}`.
2. Creates the namespace (if missing) with labels: **`app=cloud-networking-studio`**, **`project_id`** (when present), **`topology_id`**, **`deployment_id`**, plus internal `cns.io/*` labels.
3. Writes a **ConfigMap** `cns-topology-metadata` holding the deployment JSON.
4. For each plan node: a **Deployment** and a **ClusterIP Service** (port 80), with pod label **`cns.io/node-id`** for log and traffic selection.

## Destroy

The runner deletes the **entire namespace** for that deployment (idempotent if already gone). The backend passes **`project_id`** as a query parameter when the topology belongs to a project so the namespace matches the deploy path.

## Status and logs

- **`GET /deployments/{id}?topology_id=...&project_id=...`** returns JSON including **`status`** (`running`, `pending`, `failed`, `destroyed`), **`runtime_provider`**: `kubernetes`, **`namespace`**, and **`resources`** (pods, deployments, services, configmaps in that namespace).
- **`GET /deployments/{id}/logs`** uses **`node_id`**, **`topology_id`**, optional **`project_id`**, optional **`tail`**.

## Traffic tests

Ping and HTTP tests run via **kubectl exec** into the source pod, targeting the **pod IP** of the destination workload (same namespace). Images should include **`ping`** and **`wget`** (for example **alpine**).

## Limitations (today)

- **Segmented multinet** topologies are rejected (same as the Go Docker path limitation).
- No **EKS/GKE-specific** integration; any standard Kubernetes API endpoint reachable from the runner is enough.
- **Read-only runtime** views in FastAPI (inspect topology, stats) still use **docker-py** in hybrid mode; they do not yet reflect Kubernetes pod state.

## Future: managed clouds (EKS)

A likely next step is optional **IRSA / OIDC** wiring for AWS, node role policies for ELB/VPC CNI, and documenting how **`KUBECONFIG`** maps to cluster-admin vs scoped RBAC. The HTTP contract and FastAPI integration are intended to stay stable.
