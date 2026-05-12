# Demo script (UI and CLI)

Use this document to run a **repeatable** demo: what to click or type, and **what each step proves**. For automation, the authoritative shell script is [`scripts/demo_full_flow.sh`](../scripts/demo_full_flow.sh).

**Prerequisites:** Postgres + backend (`uvicorn`) + Docker Engine; for UI, `npm run dev` in `frontend/` with API reachable (Vite proxy to port 8000 is the default).

---

## Part A — Flat topology (single segment)

**Story:** two workloads on **one** L2 segment; reachability; failure; reconcile/heal; teardown.

### A.1 UI flow (exact)

1. **Open dashboard** — `http://localhost:5174` (or your Vite URL).  
   *Proves:* UI loads against live API.

2. **Create blank topology** — use dashboard control to create an empty topology; open its **detail** page.  
   *Proves:* CRUD path for topology records.

3. **Topology studio** — add **Host** and **Service** (toolbar), connect them (drag handle or **Link mode**), optionally edit link **CIDR** in the inspector, **Save layout**.  
   *Proves:* graph is persisted (nodes, links, `editor_position`).

4. **Runtime actions** — **Deploy to runtime**. Watch **deployment events** and the graph animation.  
   *Proves:* deploy pipeline, event stream, Docker provisioning.

5. **Traffic** — **Run ping test** and **Run HTTP test** (or use **Runtime actions** buttons). Open **Traffic validation**.  
   *Proves:* exec-based probes between containers; persisted traffic test rows.

6. **Failure** — **Stop service node** (injection). Refresh; graph shows degraded/stopped state where wired.  
   *Proves:* failure injection API + runtime reflection.

7. **Recovery** — **Reconcile**, then **Heal deployment** (order matters for the story: detect drift, then remediate). Re-run ping.  
   *Proves:* reconcile output + heal restarts; return to steady state.

8. **Teardown** — **Destroy deployment**.  
   *Proves:* labeled resources torn down without orphaning unrelated Docker objects.

### A.2 CLI flow (exact)

Run from repo root (same as README):

```bash
chmod +x scripts/demo_full_flow.sh   # once
API_BASE=http://127.0.0.1:8000 ./scripts/demo_full_flow.sh
```

The script’s **first half** performs: health → create topology → create host + service nodes → one link → deploy → runtime GET → ping + HTTP → stop/restart style failures → reconcile → heal → destroy.

*Proves:* identical story as UI, suitable for screen recording with `jq` pretty output.

---

## Part B — Routed multi-network topology

**Story:** **two** bridge segments (`net-a`, `net-b`), a **router** with two NICs, static endpoints/gateways, **cross-subnet** ping and HTTP, **router restart**, reconcile/heal, second destroy.

### B.1 UI flow (exact)

1. **New blank topology** → open detail page.

2. **Template** — in the studio toolbar, **Use template** → **Routed host → router → service** (appends nodes/links; does not clear existing content — start from empty for clarity).

3. **Inspect** — select each **link**; confirm `net-a` / `net-b`, gateways `10.72.0.1` / `10.73.0.1`, and endpoint IPs match the template.  
   *Proves:* multi-segment intent is visible and editable.

4. **Save layout** → **Deploy to runtime**. Inspect **Runtime networks & interfaces** (router `eth0`/`eth1`, forwarding flags, route snippets).  
   *Proves:* segmented networks + router attachment + observability fields.

5. **Routed traffic & validation** — run **Run routed ping** and **Run routed HTTP**; optional segment pings and **Restart router node**, then **Reconcile** / **Heal**, then routed ping again.  
   *Proves:* L3 path through router; resilience after container restart.

6. **Destroy deployment**.

### B.2 CLI flow (exact)

The script’s **second half** (after the flat lab) builds fixed **10.72.0.0/24** and **10.73.0.0/24** labs: `host-a`, `router-1`, `service-b` (busybox), two links with gateways and endpoint IPs, deploy, multi-segment runtime inspection, ping/HTTP including host→service, router restart via `POST .../failures/restart-node`, reconcile, heal, ping again, destroy.

*Proves:* full multinet story is automated and matches API contracts the UI uses.

---

## What to say in one sentence per phase

| Phase | One-liner |
|-------|-----------|
| Deploy | “We compile the graph into a plan and materialize Docker networks and containers.” |
| Traffic | “We prove the data plane by exec’ing ping and HTTP from real containers.” |
| Failure | “We inject stop/restart/kill to create real drift.” |
| Reconcile / heal | “We compare intent to actuals, then restart what’s broken.” |
| Routed | “Multiple `network_name`s become multiple bridges; the router forwards between segments.” |

---

## Troubleshooting (demo night)

- **502 / empty UI** — backend not running or wrong `VITE`/proxy target.
- **Deploy fails** — Docker not running; port/subnet collisions; read deployment events JSON.
- **Traffic fails** — workloads not running; wrong node IDs; for HTTP, target must listen on expected port (busybox lab uses provider/test expectations as in demo script).

See [local-development.md](local-development.md).
