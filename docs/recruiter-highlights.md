# Recruiter & interviewer highlights

Short form: **[RESUME_NOTES.md](RESUME_NOTES.md)** (three bullets + challenges) · **[ARCHITECTURE.md](ARCHITECTURE.md)** (control plane overview) · **[DEMO_SCRIPT.md](DEMO_SCRIPT.md)** (UI + CLI walkthrough).

Use this page as **resume bullets**, **LinkedIn summary fodder**, and **talking points** for infra/backend/platform roles. Tune numbers only if you measure them in your deployment.

---

## Strong resume bullets (examples — customize)

- Designed and implemented a **FastAPI control-plane API** with PostgreSQL persistence for **topology graphs**, **deployments**, and **append-only deployment events**, exposing lifecycle operations comparable to lightweight orchestrators.

- Built a **Docker-backed runtime provider** that provisions **user-defined networks and containers** from a **deployment planner**, with **label-based** resource ownership for safe teardown and reconciliation.

- Implemented **runtime inspection** (logs, stats, topology/deployment runtime views), **synthetic traffic tests** (ping/HTTP between containers), and **failure injection** (stop/restart/kill) to validate **resilience and recovery** scenarios.

- Delivered **reconciliation and self-healing APIs** that compare **desired state** in the database to **actual Docker state**, with **controller-style** scheduled passes and **heal** operations for individual deployments.

- Authored **end-to-end automation** (`scripts/demo_full_flow.sh`) demonstrating a full **Day-2 operations** story: deploy → test → break → reconcile → heal → destroy.

- Maintained **OpenAPI-first** development with **Pydantic** schemas, **CI with Postgres**, and documentation suitable for **production-adjacent** portfolio review.

---

## Architecture talking points

1. **Intent vs actuals** — topology records are desired state; Docker is actual state; APIs make the gap explicit.
2. **Provider boundary** — HTTP handlers do not embed SDK calls directly; the provider isolates **Docker** (or future runtimes).
3. **Event stream** — deployment events are a first-class **audit and demo** surface, not an afterthought.
4. **Operability** — separate paths for **read-only inspection**, **reconciliation**, and **healing** echo real control planes (Kubernetes, Terraform, ASGs).

---

## Distributed systems concepts (name these in interviews)

- **Reconciliation loop** and **drift detection**
- **Idempotent** destroy/teardown and **label-scoped** resource management
- **At-least-once** style event logging (append-only events; consumers can be added later)
- **Failure domains** at the **node/container** level; **probes** via traffic tests
- **Separation of data plane (containers)** and **control plane (API + DB)**

---

## Cloud & networking concepts

- **Virtual networks** and **L3 addressing** as modeled links and CIDRs
- **East-west** traffic validation between workloads (ping/HTTP)
- **Chaos / fault injection** for resilience testing
- **Service reachability** vs **declared links** — proving the data path works

---

## Suggested 30-second pitch

> “Cloud Networking Studio is a small control plane: you graph a network topology in Postgres, deploy it to real Docker networks and containers, run synthetic ping and HTTP tests, inject failures, then reconcile and heal drift. It’s API-first and event-logged, designed to read like a tiny slice of Kubernetes or a cloud networking control plane for a portfolio.”

---

## Honest scope statement (use if asked)

This is a **focused portfolio system**, not a managed cloud product. It demonstrates **architecture and API design** with real Docker, not web-scale multi-tenancy or HA scheduling.
