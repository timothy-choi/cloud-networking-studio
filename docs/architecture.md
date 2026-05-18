# Architecture (portfolio overview)

**In 30 seconds:** Users edit a **network graph** in the UI; the API stores that intent in **PostgreSQL** and runs **deploy / destroy / traffic / failure / reconcile / heal** flows through a **runtime provider** (Docker is the primary implementation). A **Go runtime executor** can run beside FastAPI to apply richer plans and return detailed runtime metadata for **Runtime Access** and in-network checks. **Deployment events** give an append-only audit trail suitable for demos.

This document explains **Cloud Networking Studio (CNS)** in terms a recruiter or interviewer can follow in one sitting. For API-level diagrams, sequence charts, and extra detail, see **[system-architecture.md](system-architecture.md)**. For a guided screen-share script, see **[DEMO_GUIDE.md](DEMO_GUIDE.md)**.

### Why interviewers often care

- **Clear boundary** — Domain logic and HTTP handlers stay separate from Docker (or Kubernetes) SDK calls; the provider is the seam you would extend in a real platform.
- **Orchestration-shaped verbs** — Deploy, destroy, reconcile, and heal mirror how production control planes talk about state.
- **Observable runs** — Structured events and metrics hooks show how you would operate the system, not only build it.

---

## What “control plane” means here

CNS is a **small control plane**: users describe infrastructure as data in **PostgreSQL**, and the API **plans** and **applies** changes through a **runtime provider** boundary. The UI and `curl` are clients of the same REST API.

| Concern | Where it lives |
|--------|----------------|
| Desired state | Topologies, nodes, links, deployments (SQLAlchemy + Postgres) |
| Orchestration logic | Services (planning, deploy pipeline, traffic, failures, reconcile/heal) |
| Rich apply + in-cluster probes (optional) | **Go runtime executor** — sidecar-style process the API calls for plans that need the runner |
| Actual state | Docker Engine (networks, containers, exec) — or Kubernetes when configured |
| Audit trail | Append-only **deployment events** |

Handlers stay thin: validate input, call services, return JSON. Docker SDK calls stay **inside** the provider implementation, not scattered across routes.

---

## Topology model

A **topology** is a graph:

- **Nodes** — workloads (`host`, `generic` service, `router`, `switch`, `gateway`) with `image`, optional **intent IP**, and opaque `config` (e.g. UI layout coordinates).
- **Links** — edges between two nodes: `network_name`, **CIDR**, optional **gateway**, optional **VLAN tag** (documentation), optional **source/target endpoint IPs** for static addressing on a segment.

**Flat topology:** one logical segment — typically one `network_name` across the link(s). The Docker provider maps this to a familiar single-bridge lab.

**Routed / multi-network topology:** **two or more distinct `network_name` values** on links. The planner treats the topology as **segmented**: multiple user-defined bridge networks, router containers attached to each adjacent segment, **IPv4 forwarding**, and **default routes on leaves** toward the router on that segment. Endpoint and gateway fields on links carry the addressing intent the provider uses when programming routes.

---

## Docker runtime provider

The **runtime provider** interface abstracts: deploy from a plan, destroy, logs/stats, reconcile, heal, and node-targeted operations (e.g. restart container).

The **Docker** implementation:

- Creates **bridge networks** and **containers** labeled so ownership is traceable to a topology/deployment.
- **Single-segment** labs: one `cns-topology-*` style network (legacy-friendly path).
- **Segmented** labs: **one bridge per segment** (per distinct `network_name`), deterministic **synthetic interface ordering** (`eth0`, `eth1`, …) in runtime responses, plus **`network_interfaces`** with logical network hints where available.
- **Router** nodes: elevated privileges as needed so the kernel can forward and routes can be installed; **`ip_forward`** is observable in runtime snapshots alongside **trimmed route and interface listings** from inside the container.

See [runtime-provider.md](runtime-provider.md) for naming, labels, and lifecycle specifics.

---

## Traffic tests

**Traffic tests** are first-class records: the API triggers **ICMP ping** or **HTTP** from a **source** container to a **target** node’s workload (implementation uses `docker exec` style execution against running containers). Results store stdout/stderr, exit code, latency when available, and **success** flags — suitable for UI history tables and demo scripts.

See [traffic-testing.md](traffic-testing.md).

---

## Failure injection

**Failure injection** records an intent to perturb a specific **node’s** backing container: **stop**, **restart**, or **kill** (exact semantics depend on the provider). This creates **real drift** from the last successful deploy — the kind of mess reconciliation is meant to surface.

See [failure-recovery.md](failure-recovery.md).

---

## Reconcile / heal loop

- **Reconcile** — read-only comparison (plus structured output) of **desired** topology/deployment expectations vs **live** Docker state: missing networks, stopped containers, missing node bindings, etc.
- **Heal** — **remediation** pass for a deployment: restart stopped workloads, recreate missing pieces where supported, and report what was skipped or failed.

Together they mirror **Day-2** platform operations: detect drift, then act — without hiding imperative steps behind a black box.

---

## How the pieces fit (mental model)

```text
  Client (UI / curl)
        │
        ▼
   FastAPI routes
        │
        ▼
   Services (domain logic)
        │
   ┌────┴────┐
   ▼         ▼
 Postgres   Runtime provider ──► Docker Engine
   │              │
   │              └── containers & networks
   └── deployments, events, traffic tests, failures
```

---

## See also

| Document | Audience |
|----------|----------|
| [system-architecture.md](system-architecture.md) | Deeper diagrams and request flows |
| [DEMO_SCRIPT.md](DEMO_SCRIPT.md) | Step-by-step UI and CLI demos |
| [DEMO_GUIDE.md](DEMO_GUIDE.md) | 5-minute recruiter script, impressive moments, troubleshooting |
| [RESUME_NOTES.md](RESUME_NOTES.md) | Resume bullets and interview framing |
| [failure-recovery.md](failure-recovery.md) | Reconcile/heal and failure injection detail |
| [repository-layout.md](repository-layout.md) | Where code lives in the repo |
