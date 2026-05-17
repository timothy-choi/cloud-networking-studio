# Runtime safe exec and restart (Step 42)

This document describes **safe exec mode** and **restart** operations exposed by the control plane and implemented by the Go runner (`cns-runner`). There is **no interactive shell** in the product UI or API; commands are allowlisted and validated on both the API and the runner.

## Safe exec mode

- **POST** `/deployments/{deployment_id}/runtime/services/{service_id}/exec` with body `{ "command": string, "timeout_seconds": number }` (1–120, default 10).
- `service_id` is the persisted **deployment runtime resource** id (same as other runtime operations), not an arbitrary container name.
- Every invocation is stored in **`deployment_runtime_exec_results`** (including `rejected` and `unsupported`), with `created_by_user_id` set to the caller.
- **GET** `/deployments/{deployment_id}/runtime/exec-results` — recent results (newest first).
- **GET** `/deployments/{deployment_id}/runtime/exec-results/{exec_result_id}` — one row.

### Allowlisted commands

The Python API and Go `safeexec` package enforce the same rules (keep them in sync when changing either side):

| Command | Notes |
|--------|--------|
| `whoami` | No arguments |
| `hostname` | Optional `-f` only |
| `env` | No arguments |
| `ps` | Arguments must match `[a-zA-Z0-9._-]+` |
| `ip addr` | No extra args |
| `ip route` | Optional trailing `show` |
| `cat /etc/resolv.conf` | Exact path only |
| `nslookup <target>` | Single hostname-like target |
| `curl <url>` | Single `http` or `https` URL token |
| `wget <url>` | Same as curl |
| `ping <host>` | Or `ping -c N <host>` with N in 1–10 |

### Rejection rules

Commands are rejected if they:

- Contain shell metacharacters or chaining: `;` `&` `|` `` ` `` `$` `(` `)` `>` `<` newlines, etc.
- Match dangerous substrings (e.g. `shutdown`, `reboot`, `mkfs`, package managers, `chmod`/`chown`, `rm` as first token, etc.).
- Are not exactly one of the allowlisted patterns above.

Response uses `status: "rejected"` and a `message` explaining the failure (persisted on the exec result row).

### Permissions

- **Viewer**: can read exec results and other runtime details; **cannot** POST exec or restart.
- **Member / owner**: can POST exec and restart.

## Docker behavior (runner)

- **Exec**: Resolve the container for the topology node id, then `docker exec` with the validated argv and a context timeout.
- **Restart**: `docker restart` on that container.
- If the Docker client is not configured, exec returns **`unsupported`** (HTTP 200 with JSON); restart returns **`failed`** with HTTP **503**.

## Kubernetes behavior (runner)

- **Exec**: Resolve the workload pod (by labels / deployment mapping used elsewhere in the runner), then `kubectl`-style exec with argv and timeout.
- **Restart**: Delete the pod so the owning workload controller recreates it (simple, safe pattern). Message indicates pod deletion.
- If the Kubernetes client is not initialized, exec may return **`unsupported`**; restart returns **503** with a JSON error body.

## Restart API

- **POST** `/deployments/{deployment_id}/runtime/services/{service_id}/restart` — no body.
- Response: `{ "status": "accepted" | "succeeded" | "failed" | "unsupported", "message": string, "runtime_provider": "docker" | "kubernetes" }`.
- Restart is **not** persisted as a separate table row; it is a one-shot operation. Exec results remain the audit trail for diagnostics.

## Control plane vs runner

When `RUNTIME_EXECUTOR=go` (see app settings / env), the API forwards allowlisted commands to the runner. Rejected commands are **never** sent to the runner. If the executor is not `go`, exec results are stored with `status: "unsupported"` and an explanatory message.

## Future: full interactive shell (Step 43)

A future step may add a **browser terminal** (WebSocket PTY, session recording, stricter policy). Until then, users should rely on **preset commands**, optional targets (for `nslookup` / `curl` / `wget` / `ping`), and **exec history** in the Runtime access UI.
