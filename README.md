# Cloud Networking Studio

**Design topologies, deploy to real containers, run traffic tests, inject failures, reconcile drift, and stream deployment events** — a control-plane style API for cloud and networking experimentation with a **Docker-backed runtime provider**.

---

## What Cloud Networking Studio is

**Cloud Networking Studio (CNS)** is a portfolio-grade **control plane**: you describe a network as a **persisted graph** (topologies, nodes, links with CIDRs, gateways, and optional per-segment endpoint IPs). The backend **plans** a deployment, a **Docker runtime provider** creates **real bridge networks and containers**, and the API exposes **runtime inspection**, **synthetic traffic tests** (ping / HTTP), **failure injection**, **reconciliation** against live Docker state, and **healing** — with an **append-only deployment event** stream suitable for demos and debugging.

A **React dashboard** (`frontend/`) provides a topology list, a **React Flow** studio (manual editing + templates), deploy/runtime controls, traffic history, and raw JSON views — all backed by the same REST API as `curl` and the automated demo script.

---

## Key features

| Area | What you get |
|------|----------------|
| **Topology** | CRUD for topologies, nodes, and links; per-link **CIDR**, **gateway**, **VLAN tag** (documentation), **per-link endpoint IPs** for static addressing |
| **Flat topology** | Single logical segment: one primary `network_name` pattern; classic host + service on one Docker bridge lab |
| **Routed / multi-network** | **Multiple distinct `network_name` values** → **segmented** mode: multiple user-defined bridges, **router** nodes on more than one segment, **IPv4 forwarding**, **default routes on leaves** toward the segment router |
| **Deployment** | `POST .../deploy` → real networks/containers; **destroy** for teardown; deployment status on records |
| **Events** | Per-deployment **event stream** (provision steps, warnings, errors) |
| **Runtime** | Topology- and deployment-scoped **runtime** JSON, container logs/stats, NIC lists with synthetic `eth*` ordering |
| **Controller** | Manual **reconcile** pass and per-deployment **heal** |
| **Traffic tests** | **ICMP** and **HTTP** checks executed from one container toward another node’s workload |
| **Failure injection** | **Stop**, **restart**, or **kill** a node’s backing container |
| **CI & quality** | **GitHub Actions** — pytest, frontend build, **production Compose** + HTTP smoke ([docs/CI.md](docs/CI.md)); **`scripts/demo_full_flow.sh`** for flat + routed smoke |

---

## Flat vs routed (terminology)

| Mode | Topology shape | Docker picture (simplified) |
|------|------------------|-----------------------------|
| **Flat** | One segment (e.g. one link / one `network_name`) | One lab bridge; two containers on the same L2 domain |
| **Routed** | Two+ segments (e.g. `net-a` and `net-b`) + a **router** node participating in the graph | Two bridges; router container attached to both; cross-segment traffic goes **L3 through the router** |

---

## Architecture at a glance

The system separates **declarative intent** (PostgreSQL-backed topology and deployment records) from **imperative execution** (runtime provider using the Docker SDK). Operators (or the UI) trigger **reconcile** and **heal**. **Deployment events** are an append-only audit trail.

```mermaid
flowchart LR
  subgraph control["Control plane"]
    API[FastAPI]
    DB[(PostgreSQL)]
    SVC[Services]
  end
  subgraph data["State"]
    TOPO[Topology graph]
    DEP[Deployments + events]
  end
  subgraph run["Runtime"]
    RP[Runtime provider]
    DK[Docker Engine]
  end
  API --> SVC --> DB
  TOPO --> DEP
  SVC --> RP --> DK
  API --> TOPO
```

**Portfolio-friendly docs (start here):**

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — control plane, topology model, Docker provider, traffic, failures, reconcile/heal (interviewer-oriented)
- [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) — exact **UI** and **CLI** demo steps and what each proves
- [docs/RESUME_NOTES.md](docs/RESUME_NOTES.md) — **three resume bullets**, talking points, challenges solved
- [docs/CI.md](docs/CI.md) — what GitHub Actions runs (including production Compose smoke)

**Technical deep dives:**

[docs/system-architecture.md](docs/system-architecture.md) · [docs/runtime-provider.md](docs/runtime-provider.md) · [docs/failure-recovery.md](docs/failure-recovery.md) · [docs/traffic-testing.md](docs/traffic-testing.md)

---

## System capabilities

- **Intent vs actuals:** persisted desired topology vs live Docker state; drift surfaced by **reconciliation**.
- **Provider abstraction:** runtime behavior sits behind a **provider interface**; **Docker** is the primary implementation today.
- **Orchestration-shaped API:** deploy, destroy, inspect, reconcile, heal — familiar to platform and SRE workflows.
- **Observable runs:** structured deployment events for demos and future dashboards.
- **Network modeling:** links carry **network_name**, **CIDR**, optional **gateway**, and endpoint IPs; **segmented** labs map each segment to its own Docker network with deterministic **`eth*`** ordering in runtime inspection.

---

## Continuous integration

Workflow: [.github/workflows/ci.yml](.github/workflows/ci.yml)

**Triggers:** push to **`main`**, and **all pull requests**.

**Jobs (any failure fails the run):**

| Job | What it validates |
|-----|-------------------|
| **Backend (pytest)** | Python 3.12, Postgres 16 service, `pytest tests/ -q` with `CNS_USE_FAKE_DOCKER=1` |
| **Frontend (production build)** | Node 22, `npm ci`, `npm run build` |
| **Docker (backend image)** | `docker build -f backend/Dockerfile ./backend` |
| **Docker (frontend image)** | `docker build -f frontend/Dockerfile ./frontend` |
| **Compose (prod config)** | `docker compose -f docker-compose.prod.yml config --quiet` |

**Badge placeholders** (replace `OWNER` and `REPO` with your GitHub path):

```markdown
[![CI](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/OWNER/REPO/actions/workflows/ci.yml)
```

---

## Screenshots (placeholders for your portfolio)

Add images under `docs/images/` (or your portfolio site) and link them here. Suggested captures:

| Slot | What to capture |
|------|-----------------|
| **Dashboard** | Topology list + health / create controls |
| **Topology studio — flat** | Host + service on one segment; edge label showing CIDR |
| **Topology studio — routed** | `host-a` — `net-a` — `router-1` — `net-b` — `service-b`; distinct edge colors; router badges |
| **Inspector** | Link form showing gateway + source/target endpoint IPs with node names |
| **Deployment** | Deployment timeline / event strip after **Deploy** |
| **Runtime** | Collapsible runtime section: networks, node→container mapping, router `eth0`/`eth1`, route snippet |
| **Traffic validation** | Last ping / HTTP cards + history for cross-segment tests |
| **Failure + heal** | Stopped container state → **Reconcile** → **Heal** → green traffic again |

**Markdown image example (after you add files):**

```markdown
![Topology studio](docs/images/topology-studio-routed.png)
```

---

## Quickstart

### Prerequisites

- **Python 3.11+** (see `backend/requirements.txt`)
- **PostgreSQL** (local or Docker; repo defaults use port **5433** — see [docker-compose.yml](docker-compose.yml))
- **Docker Engine** (for real networks, containers, traffic, and failure injection)
- **`curl`** and **`jq`** (for the demo script)
- **Node.js 20+** and **npm** (for the web UI in `frontend/`)

### Database

```bash
docker compose up -d postgres
export DATABASE_URL="postgresql://cns_user:cns_password@localhost:5433/cloud_networking_studio"
```

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- **OpenAPI UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health:** `GET /health`

### Frontend (dashboard)

```bash
cd frontend
cp .env.example .env   # optional — defaults use Vite proxy (/api → http://127.0.0.1:8000)
npm install
npm run dev
```

Open **http://localhost:5174**. During **`npm run dev`**, the UI uses **`/api/...`** on the same origin and **Vite proxies** to FastAPI on **8000**. Keep **`uvicorn`** running on **8000** while using the UI.

**Production build:**

```bash
cd frontend
npm run build
npm run preview   # optional — serves dist/
```

**What the UI covers:** dashboard (health, topology list), topology detail with **React Flow studio** (nodes/links, templates including **routed host → router → service**, inspector with link addressing, deployment planning), **Runtime actions** (deploy, traffic, stop-node, reconcile, heal, destroy), **Routed traffic & validation** (directed ping/HTTP, quick-path buttons), deployment events, and raw JSON panels.

### Topology studio (visual builder)

- **Add nodes** (host, service, router, switch) or **Use template** (client/server, tiers, load balancer, router/switch, mesh, **routed host → router → service**).
- **Connect** nodes (handles or **Link mode**); edit **CIDR / gateway / endpoint IPs** in the inspector.
- **Save layout** persists `config.editor_position` via PATCH.
- **Keyboard:** Delete/Backspace removes selection; **⌘/Ctrl+S** saves layout; **⌘/Ctrl+D** duplicates node; **F** fits view.

---

## Demo commands

**Automated (recommended)** — flat lab immediately followed by routed multinet lab:

```bash
chmod +x scripts/demo_full_flow.sh   # once
./scripts/demo_full_flow.sh
```

```bash
API_BASE=http://127.0.0.1:8000 ./scripts/demo_full_flow.sh
```

Step-by-step narration for **UI** and **CLI**: [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

**Production-style stack** (Postgres + API + static UI + Caddy on port **80**): [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) · [docs/EC2_RUNBOOK.md](docs/EC2_RUNBOOK.md) · `docker-compose.prod.yml` · copy [.env.example](.env.example) to `.env`.

---

## Routed topology example (curl)

Same addressing as `scripts/demo_full_flow.sh` part B: **10.72.0.0/24** (`net-a`) and **10.73.0.0/24** (`net-b`). Replace `TOPOLOGY_ID`, `HOST_ID`, `ROUTER_ID`, `SERVICE_ID` with UUIDs returned by your API.

```bash
API=http://localhost:8000

# Topology
curl -s -X POST "$API/topologies" -H 'Content-Type: application/json' \
  -d '{"name":"Routed readme demo","description":"two segments","runtime_target":"docker","networking_mode":"docker_bridge","status":"draft"}' | jq .

# Nodes: host-a (10.72.0.10), router-1, service-b (10.73.0.20, busybox)
curl -s -X POST "$API/topologies/TOPOLOGY_ID/nodes" -H 'Content-Type: application/json' \
  -d '{"name":"host-a","node_type":"host","image":"alpine:latest","ip_address":"10.72.0.10","config":null}' | jq .
curl -s -X POST "$API/topologies/TOPOLOGY_ID/nodes" -H 'Content-Type: application/json' \
  -d '{"name":"router-1","node_type":"router","image":"alpine:latest","ip_address":null,"config":null}' | jq .
curl -s -X POST "$API/topologies/TOPOLOGY_ID/nodes" -H 'Content-Type: application/json' \
  -d '{"name":"service-b","node_type":"generic","image":"busybox:1.36","ip_address":"10.73.0.20","config":null}' | jq .

# Links: host→router on net-a; router→service on net-b
curl -s -X POST "$API/topologies/TOPOLOGY_ID/links" -H 'Content-Type: application/json' \
  -d '{"source_node_id":"HOST_ID","target_node_id":"ROUTER_ID","network_name":"net-a","cidr":"10.72.0.0/24","gateway":"10.72.0.1","source_endpoint_ip":"10.72.0.10","target_endpoint_ip":"10.72.0.1","config":null}' | jq .
curl -s -X POST "$API/topologies/TOPOLOGY_ID/links" -H 'Content-Type: application/json' \
  -d '{"source_node_id":"ROUTER_ID","target_node_id":"SERVICE_ID","network_name":"net-b","cidr":"10.73.0.0/24","gateway":"10.73.0.1","source_endpoint_ip":"10.73.0.1","target_endpoint_ip":"10.73.0.20","config":null}' | jq .

# Deploy + cross-segment traffic (use returned deployment id for reconcile/heal)
curl -s -X POST "$API/topologies/TOPOLOGY_ID/deploy" | jq .
curl -s -X POST "$API/topologies/TOPOLOGY_ID/traffic-tests/ping" -H 'Content-Type: application/json' \
  -d '{"source_node_id":"HOST_ID","target_node_id":"SERVICE_ID","count":3}' | jq .
curl -s -X POST "$API/topologies/TOPOLOGY_ID/traffic-tests/http" -H 'Content-Type: application/json' \
  -d '{"source_node_id":"HOST_ID","target_node_id":"SERVICE_ID","path":"/","port":80}' | jq .
```

In the **UI**, you can append the same graph with **Use template → Routed host → router → service** instead of typing `curl`.

---

## API examples (short)

Replace UUIDs with values from your session.

```bash
curl -s -X POST "http://localhost:8000/topologies/<topology_id>/deploy" | jq .
curl -s "http://localhost:8000/deployments/<deployment_id>/runtime" | jq .
curl -s -X POST "http://localhost:8000/topologies/<topology_id>/traffic-tests/ping" \
  -H "Content-Type: application/json" \
  -d '{"source_node_id":"<uuid>","target_node_id":"<uuid>","count":3}' | jq .
curl -s -X POST "http://localhost:8000/deployments/<deployment_id>/reconcile" | jq .
curl -s -X POST "http://localhost:8000/deployments/<deployment_id>/heal" | jq .
curl -s -X POST "http://localhost:8000/deployments/<deployment_id>/destroy" | jq .
```

Full Docker naming and labels: [docs/runtime-provider.md](docs/runtime-provider.md).

---

## Demo flow (`scripts/demo_full_flow.sh`)

**A. Flat single-bridge lab** — host + service, one link, deploy, runtime, ping/HTTP, failures, reconcile/heal, destroy.

**B. Routed lab** — `host-a → router-1 → service-b` across **net-a** / **net-b**, cross-segment ping/HTTP, **router restart**, reconcile/heal, destroy.

This script is the **authoritative smoke test** next to `pytest`.

---

## Failure injection & healing

**Failure injection** applies Docker-level actions to a node’s container (stop / restart / kill semantics per provider), creating **real drift**.

**Reconciliation** compares desired records to live Docker (networks, containers, stopped processes).

**Healing** attempts to restore stopped or missing pieces for a deployment.

Details: [docs/failure-recovery.md](docs/failure-recovery.md)

---

## Roadmap

| Horizon | Direction |
|---------|-----------|
| **Near** | Authn/z, multi-tenant guardrails, richer metrics on deployments |
| **Near** | Metrics export (Prometheus), structured logging, trace IDs |
| **Mid** | Additional runtime targets (e.g. Kubernetes, compose stacks) |
| **Mid** | Richer network policies, bandwidth/latency emulation |
| **Long** | Plugin telemetry providers, chaos schedules, collaboration |

UI notes: [docs/frontend-mvp-and-observability.md](docs/frontend-mvp-and-observability.md)

---

## Documentation index

**Note:** The long-form diagram doc was renamed to **[docs/system-architecture.md](docs/system-architecture.md)** so it sits beside **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** on case-insensitive file systems (macOS default volumes).

| Doc | Purpose |
|-----|---------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Portfolio architecture overview (control plane, topology, Docker, reconcile/heal) |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production Compose, EC2, troubleshooting, next infra steps |
| [docs/EC2_RUNBOOK.md](docs/EC2_RUNBOOK.md) | Single-instance EC2: Docker, clone, `.env`, compose, smoke, cleanup |
| [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) | Exact UI + CLI demo flows |
| [docs/RESUME_NOTES.md](docs/RESUME_NOTES.md) | Three resume bullets, talking points, challenges |
| [docs/system-architecture.md](docs/system-architecture.md) | Detailed design, diagrams, API flow |
| [docs/runtime-provider.md](docs/runtime-provider.md) | Docker mapping, lifecycle, labels |
| [docs/failure-recovery.md](docs/failure-recovery.md) | Reconciliation, healing, failure injection |
| [docs/traffic-testing.md](docs/traffic-testing.md) | Ping/HTTP execution model |
| [docs/repository-layout.md](docs/repository-layout.md) | Repository layout |
| [docs/local-development.md](docs/local-development.md) | Dev setup, troubleshooting |
| [docs/testing.md](docs/testing.md) | Running tests locally / CI |
| [docs/recruiter-highlights.md](docs/recruiter-highlights.md) | Extra bullets and pitch variants |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |

---

---

## License

License not specified in this repository; add a `LICENSE` file when you publish publicly.
