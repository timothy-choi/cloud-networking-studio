# Resume notes

Short, high-signal material for **resumes**, **LinkedIn**, and **phone screens**. For a longer bullet list and pitch variants, see [recruiter-highlights.md](recruiter-highlights.md).

---

## Three strong resume bullets

1. **Built a FastAPI + PostgreSQL control plane** that models **network topologies as graphs** (nodes, links, CIDRs, gateways, per-segment endpoint IPs), persists **deployments and append-only events**, and exposes lifecycle APIs (**deploy**, **destroy**, **runtime**, **reconcile**, **heal**) similar to lightweight orchestrators.

2. **Implemented a Docker runtime provider** that maps topology intent to **bridge networks and containers** — including **multi-segment (routed) labs** with interface-ordered runtime inspection, **IPv4 forwarding** on router workloads, and **label-scoped** teardown for safe reconciliation.

3. **Shipped operability and validation surfaces**: **synthetic traffic tests** (ping/HTTP between containers), **failure injection** (stop/restart/kill), **reconciliation vs live Docker state**, a **React topology studio** (templates, inspector, deploy controls), and an **end-to-end bash demo** covering flat and routed paths.

---

## Interview talking points

- **Intent vs actuals** — Topology rows are desired state; Docker is actual state; reconcile makes the gap visible, heal attempts closure.
- **Provider boundary** — HTTP handlers do not own Docker SDK details; swapping runtimes means swapping providers, not rewriting all routes.
- **Why routed is interesting** — Multiple `network_name`s flip the planner into **segmented** mode: multiple bridges, multi-homed router, static routes on leaves — closer to real multi-tier networking than a single flat bridge.
- **Observability** — Deployment events are an audit log; runtime payloads expose NICs, forwarding, and trimmed **route / interface** views for demos.
- **Honest scope** — Portfolio-scale system: single tenant, manual controller hooks, not Kubernetes-level scheduling or multi-region HA.

---

## Technical challenges solved (sound bites)

| Challenge | How you addressed it |
|-----------|----------------------|
| **Static IPs on Docker bridges** | Per-link **endpoint IPs** and **gateways** in the topology model; provider logic avoids IPAM/gateway collisions and programs leaf routes toward the router segment IP. |
| **Router between segments** | Router **node type** with attachments to each segment network, **ip_forward**, and privileged capabilities only where the data plane requires it. |
| **Drift and recovery** | **Reconcile** structured diff of expected vs Docker; **heal** restarts/repairs per deployment; **failure injection** creates realistic stopped-container scenarios. |
| **Explainability** | Event stream + runtime projection + UI graph (segment-colored edges, router badges) so demos read as a story, not a black box. |

---

## 30-second pitch (verbatim optional)

> “Cloud Networking Studio is a control-plane style API: you model a network as a graph in Postgres, deploy it to real Docker networks and containers, run ping and HTTP traffic tests, inject failures, then reconcile and heal drift. It includes a routed multi-segment lab so you can show L3 forwarding, not just a flat bridge — it’s meant to read like a thin slice of platform networking work.”
