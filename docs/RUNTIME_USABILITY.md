# Runtime usability (Step 49)

Step 49 makes deployed topologies easier to **use** in real workflows: integration snippets, topology→runtime mapping, and an optional interactive terminal.

## Use this deployment

**GET** `/deployments/{id}/runtime/integration` returns:

- Internal and exposed endpoints
- Suggested environment variables (`CNS_SERVICE_URL`, deployment/topology IDs)
- **Connect your app** summary (local, CI, service URLs)
- Generated snippets: curl, Python `requests`, Node `fetch`, `docker exec`, `kubectl` commands, GitHub Actions example
- Full `instructions` object (same keys as Step 39)

The UI **Use deployment** tab loads this endpoint and provides **Copy** buttons per snippet.

## Topology → Runtime mapping

**GET** `/deployments/{id}/runtime/mapping` returns rows linking:

- Topology node id / name
- Persisted runtime resource id and type
- Container or pod name
- Internal / external URLs
- Namespace or Docker network

## Interactive terminal

| Method | Path | Role |
|--------|------|------|
| POST | `/deployments/{id}/runtime/services/{service_id}/terminal` | Open session (member/owner) |
| DELETE | `/terminal-sessions/{session_id}` | Close session |
| WebSocket | `/terminal-sessions/{session_id}/ws?token=…` | Attach shell |

- **Docker**: backend attaches `docker exec` TTY when the engine is reachable (`RUNTIME_EXECUTOR=python` or `go` with Docker socket on the API host).
- **Kubernetes**: session is created but the WebSocket returns guidance to use `kubectl exec` / port-forward snippets (full in-cluster attach is deferred).
- **Fake Docker** (`CNS_USE_FAKE_DOCKER=1`): simulated echo terminal for CI.
- Audited via deployment events; idle timeout and max duration from env (`TERMINAL_*` settings).
- **Safe exec** (allowlisted commands) remains the default diagnostic path; terminal is advanced.

## Permissions

- Viewers: read integration/mapping/runtime APIs; cannot open terminal, expose, exec, or restart.
- Members/owners: full runtime operations including terminal.

## Related docs

- [RUNTIME_ACCESS.md](RUNTIME_ACCESS.md) — persisted resources and instructions
- [RUNTIME_EXEC_RESTART.md](RUNTIME_EXEC_RESTART.md) — safe exec
- [SERVICE_EXPOSURE.md](SERVICE_EXPOSURE.md) — external URLs
