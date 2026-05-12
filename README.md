# Cloud Networking Studio

**Design topologies, deploy to real containers, run traffic tests, inject failures, reconcile drift, and stream deployment events** — a control-plane style API for cloud and networking experimentation with a **Docker-backed runtime provider**.

Cloud Networking Studio (CNS) models infrastructure as a persisted **topology graph** (nodes, links, addressing intent), maps it to a **deployment plan**, provisions **Docker networks and workloads**, exposes **runtime inspection**, **traffic validation**, **failure injection**, and **reconciliation / self-healing** APIs — similar to how orchestrators expose intent, state, and remediation hooks.

---

## Architecture at a glance

The system separates **declarative intent** (PostgreSQL-backed topology and deployment records) from **imperative execution** (runtime provider: Docker SDK). A **manual controller** can run reconciliation passes and targeted healing. **Deployment events** provide an append-only audit trail suitable for demos, debugging, and future streaming UIs.

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

**Deep dives:** [docs/architecture.md](docs/architecture.md) · [docs/runtime-provider.md](docs/runtime-provider.md) · [docs/failure-recovery.md](docs/failure-recovery.md) · [docs/traffic-testing.md](docs/traffic-testing.md)

---

## Features

| Area | What you get |
|------|----------------|
| **Topology** | CRUD for topologies, nodes, and links; per-link **CIDR**, **gateway**, **VLAN tag** (doc), and **per-link endpoint IPs** for multi-homed routers |
| **Multi-network routing** | When links use **more than one** `network_name`, the Docker provider creates **multiple bridge networks**, attaches routers to several segments, enables **IPv4 forwarding**, and applies **static default routes** on leaves |
| **Deployment** | Deploy topology → real Docker networks/containers; destroy/teardown; deployment status |
| **Events** | Per-deployment event stream (provision steps, warnings, errors) |
| **Runtime** | Topology/deployment runtime views, container logs/stats, reconciliation API |
| **Controller** | Controller status, manual reconcile pass, single-deployment heal |
| **Traffic tests** | ICMP ping and HTTP checks executed from one container to another |
| **Failure injection** | Stop, restart, or kill a node’s container for resilience scenarios |
| **CI & quality** | Automated tests; demo script for end-to-end validation |

---

## System capabilities

- **Intent vs actuals:** persisted desired topology vs live Docker state; drift detection via reconciliation.
- **Provider abstraction:** runtime behavior is behind a provider interface; today **Docker** is the primary implementation.
- **Orchestration-shaped API:** deploy, destroy, inspect, heal — familiar to platform and SRE workflows.
- **Observable runs:** structured deployment events for demos and future dashboards.
- **Network modeling:** links carry **network_name**, **CIDR**, optional **gateway**, and endpoint IPs; single-network labs still map to one `cns-topology-*` bridge; **segmented** labs map each segment to its own Docker network with deterministic `eth*` ordering in runtime inspection.

---

## Screenshots & UI

The current repository is **API-first** with an optional **React dashboard** in `frontend/` (topology overview, graph, deploy/runtime controls).

**Placeholder slots for your portfolio / README visuals:**

| Slot | Suggested capture |
|------|-------------------|
| **Topology** | API response or future canvas showing nodes and links |
| **Deployment** | Deployment record + event timeline after `deploy` |
| **Runtime** | `GET .../runtime` JSON or Docker `ps` aligned to topology |
| **Traffic test** | Ping/HTTP test result with stdout/latency |
| **Failure + heal** | Event sequence: inject failure → reconcile → heal |

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

The React dashboard talks to the API over **`fetch`**. Configure the backend URL (defaults match local dev):

```bash
cd frontend
cp .env.example .env   # optional — defaults use Vite proxy (/api → http://127.0.0.1:8000)
npm install
npm run dev
```

Then open **http://localhost:5174**. During **`npm run dev`**, the UI calls **`/api/...`** on the same origin and **Vite proxies** those requests to FastAPI on port **8000**, which avoids common browser issues with cross-origin `fetch` to `http://localhost:8000`. Keep the backend running (`uvicorn ... --port 8000`). The FastAPI app still enables **CORS** for direct calls from `http://localhost:5174` if you set `VITE_API_BASE_URL=http://127.0.0.1:8000` instead.

Keep the backend running on port **8000** while using the UI.

**Production build:**

```bash
cd frontend
npm run build
npm run preview   # optional — serves dist/
```

**What the UI covers:** dashboard with health + topology list, topology detail with **interactive React Flow topology studio** (add nodes/links, drag, templates, save layout to `editor_position`, inspector, deployment planning), deploy/teardown, runtime JSON, deployment events, ping/HTTP traffic tests, stop-node failure injection, reconcile, and heal — aligned with existing REST endpoints.

### Topology studio (visual builder)

Open any topology from the dashboard. The **Topology studio** pane is an editable React Flow canvas:

- **Add nodes** from the toolbar (host, service, router, switch) or **Quick create** templates (client/server, multi-tier web, load balancer, router/switch, full mesh).
- **Drag** nodes; **connect** handles to create links (default subnet is filled in—edit in the inspector).
- **Save topology** persists node positions into each node’s `config.editor_position` (merged via PATCH) so layout survives refresh.
- **Inspector** (right): rename the topology, edit node fields (name, type, image, intent IP, config JSON), and link fields (network name, CIDR, metadata JSON).
- **Deployment planning** summarizes counts, duplicate intent IPs, overlapping IPv4 subnets (best effort), and simple readiness checks.
- **Keyboard:** Delete/Backspace removes the selected link or node; **⌘/Ctrl+S** saves layout; **⌘/Ctrl+D** duplicates the selected node; **F** zooms to fit.
- **Deploy topology** in the toolbar calls the same `POST /topologies/{id}/deploy` as **Runtime controls** below—use either entry point.

Runtime polling continues to light up **workload / runtime IP / link animation** on the graph without discarding local drag positions.


### Automated demo (recommended)

From the repo root (backend running; Docker optional for full runtime behavior):

```bash
chmod +x scripts/demo_full_flow.sh   # once
./scripts/demo_full_flow.sh
```

Override the API base if needed:

```bash
API_BASE=http://127.0.0.1:8000 ./scripts/demo_full_flow.sh
```

---

## API examples

Replace UUIDs with values from your session.

**Create a topology**

```bash
curl -s -X POST "http://localhost:8000/topologies" \
  -H "Content-Type: application/json" \
  -d '{"name":"demo","description":"readme","runtime_target":"docker","networking_mode":"docker_bridge","status":"draft"}' | jq .
```

**Deploy**

```bash
curl -s -X POST "http://localhost:8000/topologies/<topology_id>/deploy" | jq .
```

**Runtime snapshot**

```bash
curl -s "http://localhost:8000/deployments/<deployment_id>/runtime" | jq .
```

**Ping traffic test**

```bash
curl -s -X POST "http://localhost:8000/topologies/<topology_id>/traffic-tests/ping" \
  -H "Content-Type: application/json" \
  -d '{"source_node_id":"<uuid>","target_node_id":"<uuid>","count":3}' | jq .
```

**Reconcile and heal**

```bash
curl -s -X POST "http://localhost:8000/deployments/<deployment_id>/reconcile" | jq .
curl -s -X POST "http://localhost:8000/deployments/<deployment_id>/heal" | jq .
```

**Teardown**

```bash
curl -s -X POST "http://localhost:8000/deployments/<deployment_id>/destroy" | jq .
```

Full tag and naming conventions for Docker resources are described in [docs/runtime-provider.md](docs/runtime-provider.md).

---

## Demo flow (`scripts/demo_full_flow.sh`)

The script runs **two labs** back-to-back:

**A. Single-bridge lab (backward compatible)** — comparable to a flat L2 segment:

1. Health check  
2. Create topology (`runtime_target: docker`)  
3. Add nodes (Alpine “host” + Nginx “service”)  
4. Add one link (subnet/CIDR)  
5. Deploy → Docker network and containers  
6. Runtime inspection  
7. Ping and HTTP traffic tests  
8. Failure injection (stop service, restart host)  
9. Reconciliation and healing  
10. Destroy deployment  

**B. Routed multi-network lab** — `host-a → router-1 → service-b` across **two** bridge networks with per-link gateways and endpoint IPs; cross-subnet ping/HTTP; **router restart**; reconcile/heal; second destroy.

It is the **authoritative smoke test** for “platform-like” behavior alongside unit/integration tests.

---

## Failure injection & healing

**Failure injection** calls Docker operations on containers backing topology nodes (stop, restart, SIGKILL-style kill depending on provider behavior). That creates **real drift** from the last known good deployment state.

**Reconciliation** compares desired topology/deployment expectations to live Docker state (networks, containers, stopped processes) and records structured findings.

**Healing** attempts to restore missing or stopped resources according to provider logic (e.g. restart containers, recreate missing pieces where supported).

Details: [docs/failure-recovery.md](docs/failure-recovery.md)

---

## Roadmap

| Horizon | Direction |
|---------|-----------|
| **Near** | Web UI for topology editing, deployment timeline, runtime tables |
| **Near** | Metrics export (Prometheus), structured logging, trace IDs |
| **Mid** | Additional runtime targets (e.g. Kubernetes, compose stacks) |
| **Mid** | Richer network policies, bandwidth/latency emulation |
| **Long** | Plugin telemetry providers, chaos schedules, collaboration |

Productized frontend and observability notes: [docs/frontend-mvp-and-observability.md](docs/frontend-mvp-and-observability.md)

---

## Documentation index

| Doc | Purpose |
|-----|---------|
| [docs/architecture.md](docs/architecture.md) | End-to-end design, diagrams, API flow |
| [docs/runtime-provider.md](docs/runtime-provider.md) | Docker mapping, lifecycle, labels |
| [docs/failure-recovery.md](docs/failure-recovery.md) | Reconciliation, healing, failure injection |
| [docs/traffic-testing.md](docs/traffic-testing.md) | Ping/HTTP execution model |
| [docs/repository-layout.md](docs/repository-layout.md) | Repository layout and conventions |
| [docs/local-development.md](docs/local-development.md) | Dev setup, env vars, troubleshooting |
| [docs/testing.md](docs/testing.md) | Running tests in CI and locally |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |
| [docs/recruiter-highlights.md](docs/recruiter-highlights.md) | Resume bullets and talking points |

---

## Why this project matters (hiring)

Concise talking points for recruiters and hiring managers: **[docs/recruiter-highlights.md](docs/recruiter-highlights.md)**

---

## License

License not specified in this repository; add a `LICENSE` file when you publish publicly.
