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
| **Topology** | CRUD for topologies, nodes, and links; runtime target and networking mode on the topology |
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
- **Network modeling:** links and CIDR-style addressing inform how Docker networking is planned and tested.

---

## Screenshots & UI

The current repository is **API-first**. A browser UI is planned (see [docs/frontend-mvp-and-observability.md](docs/frontend-mvp-and-observability.md)).

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

The script exercises a **happy path** comparable to a small cloud/network lab:

1. Health check  
2. Create topology (`runtime_target: docker`)  
3. Add nodes (e.g. Alpine “host” + Nginx “service”)  
4. Add a link (subnet/CIDR)  
5. Deploy → Docker networks and containers  
6. Runtime inspection  
7. Ping and HTTP traffic tests  
8. Failure injection (stop / restart / kill)  
9. Reconciliation and healing  
10. Destroy deployment and cleanup-related steps as implemented  

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
| **Mid** | Richer network policies, multi-subnet topologies, bandwidth/latency emulation |
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
