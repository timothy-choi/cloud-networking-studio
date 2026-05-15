# Observability (Step 32)

Cloud Networking Studio exposes **read-only aggregates** and **rich per-deployment signals** so operators can see what the control plane did, whether runtime matches intent, and where failures occurred—without changing deploy or destroy behavior.

## Dashboard (`/`)

The main dashboard polls:

- **`GET /health`** — process liveness (unchanged).
- **`GET /controller/status`** — controller mode and managed/active deployment counts (unchanged).
- **`GET /metrics/summary`** — cross-topology counters and a short **latest deployment events** feed.

Use the **Observability** card for at-a-glance totals: topologies, active vs failed deployments, traffic test and failure-injection failure rates, and the newest deployment log lines across all labs. Each event row links to the topology (`topology_id`) so you can jump into the studio for deeper inspection.

## Per-topology studio (`/topologies/:id`)

### Runtime health

The **runtime metrics** strip summarizes:

- Deployment **status** from the latest deployment record.
- **Container** counts (total / running / stopped).
- **Network** count from the live Docker snapshot.
- **Last runtime inspection** and event poll times.
- **Latest warning or error** parsed from the deployment event stream (most recent non-info line).

These values come from existing **`GET …/runtime`** and **`GET …/deployments/:id/events`** responses—no new runtime behavior.

### Deployment timeline

**Deployment history** merges:

- Append-only **deployment events** (provision, reconcile, heal, destroy).
- **Traffic tests** and **failure injections** for the topology.

Each row shows a **phase label** (e.g. *Network*, *Containers*, *Reconcile / heal*) derived from message text, plus severity coloring. Use the **search** box to narrow rows by substring (client-side on the merged list).

### Deployment events panel

The **Deployment events** stream supports:

- **Level filter** — all / info / warning / error / debug.
- **Newest first** toggle (sort in the UI).
- **Search** — substring match on `message` (client-side).

The API also supports **`GET /deployments/{id}/events?order=asc|desc&level=…&q=…`** for scripted queries or future server-driven filters (default **`order=asc`** preserves older clients).

### Failure surfacing

When **Deploy**, **traffic**, **reconcile**, or **heal** fails, the UI shows:

1. The **exact backend message** (from FastAPI `detail` when present).
2. A **suggested next action** when the error pattern is recognized (e.g. 409 active deployment → destroy first).
3. **Expandable raw JSON** of the error payload for copy/paste into tickets or logs.

## Metrics summary API

`GET /metrics/summary`

| Field | Meaning |
|-------|---------|
| `total_topologies` | Rows in `topologies`. |
| `total_deployments` | All deployment records. |
| `active_deployments` | Docker deployments with `status=succeeded` (matches controller “live workload”). |
| `failed_deployments` | `status=failed`. |
| `total_traffic_tests` / `failed_traffic_tests` | Traffic test rows; failed = terminal `failed` status. |
| `total_failure_injections` / `failed_failure_injections` | Failure injection rows; failed = terminal `failed` status. |
| `latest_events` | Newest deployment events across all topologies (bounded list). Each row includes **`id`** (event id), **`topology_id`**, **`deployment_id`**, **`level`**, **`message`**, **`created_at`**. |

This endpoint is **read-only** and safe to poll from the dashboard or an external status board.

## Why this helps operators

- **Timeline + phases** reduce time-to-understand during demos and incidents (“did we get past networks before failing?”).
- **Metrics summary** answers “is anything broken globally?” without opening every topology.
- **Explicit error text + hints** shorten the loop from red UI to corrective action (destroy stuck deploy, fix validation, check Docker).
- **Filters and search** keep dense event streams usable as labs grow.

For architecture context, see [ARCHITECTURE.md](ARCHITECTURE.md) and [frontend-mvp-and-observability.md](frontend-mvp-and-observability.md).
