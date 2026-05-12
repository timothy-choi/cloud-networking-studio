# Frontend MVP & observability roadmap

This document plans **Step N+1** after the API-first milestone: a minimal UI and an observability layer that turn Cloud Networking Studio into a **credible demo product** without rewriting the backend.

---

## Frontend MVP (suggested scope)

### Goals

- Visualize **topology** (nodes + links) and basic metadata.
- Trigger **deploy**, **destroy**, **reconcile**, **heal** with clear confirmation and error display.
- Show **deployment events** as a live-ish timeline (polling first; SSE later).
- Surface **traffic test** results and **failure injections** as structured cards.

### Non-goals (initially)

- Multi-user auth and RBAC (add **after** core flows feel solid).
- Full canvas editing parity with production diagramming tools — start with **forms + simple graph layout**.

### Technical approach

| Option | Pros | Cons |
|--------|------|------|
| **React + Vite + TanStack Query** | Familiar hiring-manager stack; great API integration | More boilerplate |
| **Next.js** | Routing + API routes if needed later | Heavier if purely static to FastAPI |

Recommend **Vite + React** calling **OpenAPI-generated** or hand-typed clients from `/openapi.json`.

### Screen map

1. **Topology list / create**
2. **Topology detail** — nodes table, links table, CIDR display
3. **Deploy** — button → deployment detail
4. **Deployment detail** — status + **event timeline** (poll `GET /deployments/{id}/events` every 1–3s while active)
5. **Runtime** — tab showing merged API from `/topologies/{id}/runtime` or `/deployments/{id}/runtime`
6. **Traffic lab** — forms for ping/HTTP; show last result stdout/latency
7. **Chaos lab** — stop/restart/kill with safeguards (confirm modal)

### Polling vs streaming

- **Phase 1:** HTTP polling for deployment events and runtime (simplest, works everywhere).
- **Phase 2:** **SSE** (`text/event-stream`) from FastAPI for deployment events — optional backend addition; keep polling fallback.

---

## Observability & dashboard layer

### Metrics (Prometheus-friendly)

Expose counters/histograms from the FastAPI app or sidecar:

- Deployments started/succeeded/failed
- Reconciliation outcomes (drift detected yes/no)
- Traffic test success rate and latency histogram
- Failure injections by type

### Logging

- Structured JSON logs with **trace/request id** middleware.
- Correlate deployment id + topology id on every mutating route.

### Dashboards

- **Grafana** dashboards: deployment throughput, drift rate, mean recovery time (derived from events if timestamps are consistent).

### Tracing (later)

- OpenTelemetry hooks around provider calls (Docker SDK latency spans).

---

## Backend facilitators (incremental)

These are **optional** API additions when you are ready; they do not block an MVP UI:

| Addition | Why |
|----------|-----|
| `GET /deployments?topology_id=` | Easier UI navigation |
| Pagination on events | Large deployments |
| WebSocket/SSE for events | Lower latency timelines |

---

## Success criteria for “portfolio ready” UI

- A non-technical viewer can follow **deploy → see events → run ping → break node → heal** without reading curl docs.
- Screenshots map cleanly to README placeholders.
- No secrets in the browser; CORS configured explicitly for dev/prod origins.

---

## Related docs

- [system-architecture.md](system-architecture.md)
- [local-development.md](local-development.md)
