# Local demo checklist

Use this list when validating Cloud Networking Studio on a developer machine with Docker Compose (API behind Caddy at `http://localhost/api`).

## 1. Start stack

- Bring up the stack described in the repository README (Postgres, API, runner as applicable, Caddy, frontend).
- Confirm `GET http://localhost/api/health` returns JSON with `"status":"ok"`.
- Optional: `GET http://localhost/api/runtime/status` — check `backend_status`, `docker_reachable` / `runner_reachable`, and `runtime_provider`.

## 2. Projects and topologies

- Create a project and a simple topology (two nodes, one link, Docker runtime).
- Save the topology and note IDs for API/CLI use.

## 3. Deploy

- Deploy from the UI or `python3 -m cli.cns deploy --topology-id <uuid>` (with `PYTHONPATH` set to the repo root and token configured).
- `cns wait --deployment-id <uuid>` until status is `succeeded`.

## 4. Runtime access

- Open the deployment runtime view; confirm nodes/services appear.
- Use runtime logs and metrics where enabled.

## 5. Expose a service

- Create a service exposure (port forward / host port) per UI or API.
- Hit the exposed URL or documented host port from your workstation.

## 6. Logs, health, traffic

- Fetch logs for a node from the UI or API.
- Run a runtime health check on a service that exposes HTTP.
- Run ping/HTTP traffic tests between nodes if your topology supports them.

## 7. Safe exec and restart

- Use the Exec tab with allowlisted commands only (no arbitrary shell).
- Restart a workload from the UI when supported.

## 8. Templates

- Save the topology as a template; clone it into another project or name.
- Deploy the cloned topology end-to-end.

## 9. CLI lifecycle

- `cns config get` — verify `effective_base_url` (default `http://localhost/api` unless overridden).
- `cns deploy` / `wait` / `runtime` / `destroy` against the same deployment.

## 10. Cleanup stale Docker resources

- After failed experiments, use `scripts/cleanup_cns_docker.sh` (filters `label=app=cloud-networking-studio`) or `POST /api/deployments/{id}/destroy` / `POST .../runtime/cleanup` for a specific deployment.
- If you see `Pool overlaps with other one on this address space`, run cleanup then redeploy; newer builds pick alternate subnets when the topology requests an explicit `/24` that collides.
