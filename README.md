# Cloud Networking Studio

**Cloud Networking Studio (CNS)** is a full-stack cloud and networking lab platform: model topologies as graphs (nodes, links, services), deploy them to **Docker** (with an optional **Go runtime executor**), inspect live runtime state, run traffic and failure experiments, export integration artifacts and IaC, and operate deployments with versioning, profiles, and team roles. It is a **portfolio-grade control plane** — not a commercial SaaS — with **staging and production** deploy paths you can demo end-to-end.

---

## Features

- **Projects & auth** — JWT login, project scoping, roles (viewer / member / owner), email invitations, API tokens
- **Topology studio** — React Flow editor; nodes (host, router, service, …), links with CIDR/gateway; flat and multi-segment routed labs
- **Deploy & runtime** — Real Docker networks/containers; deployment events; runtime inspection; reconcile / heal; destroy
- **Traffic & failures** — ICMP/HTTP tests from inside the lab; stop/restart container failure injection
- **Integration outputs** — Env snippets, scripts, CI examples, downloadable files per deployment
- **IaC export** — Docker Compose, Kubernetes, **Terraform**, and **Ansible** zip downloads (preview with validation warnings)
- **Versioning & profiles** — Save topology versions, diff, rollback (with optional destroy); deployment profiles for env/image overrides
- **Observability & ops** — Platform/project/deployment metrics, notifications, audit logs, onboarding checklist

**Experimental / optional:** `runtime_target=kubernetes` via the Go runner (Docker remains the default for local and production EC2 stacks). See [docs/KUBERNETES_RUNTIME.md](docs/KUBERNETES_RUNTIME.md).

---

## Architecture (short)

```mermaid
flowchart LR
  UI[React SPA] --> API[FastAPI]
  API --> DB[(PostgreSQL)]
  API --> SVC[Services]
  SVC --> RP[Runtime provider]
  RP --> DK[Docker Engine]
  API -. optional .-> RUN[Go runner]
  RUN --> DK
```

**Intent** lives in Postgres (topologies, deployments, versions, profiles). **Execution** goes through a provider boundary (Python Docker SDK and/or Go runner). The UI and `curl` use the same REST API.

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## Tech stack

| Layer | Stack |
|-------|--------|
| Frontend | React, TypeScript, Vite, React Flow, Tailwind |
| Backend | Python 3.12, FastAPI, SQLAlchemy, Alembic |
| Data | PostgreSQL |
| Runtime | Docker Engine; optional `cns-runner` (Go) |
| Infra | Terraform (EC2/VPC), Ansible playbooks, GitHub Actions, Caddy, Vercel (SPA) |

---

## Quick demo (≈5 min)

1. **Register / sign in** → dashboard (starter project created on register).
2. **Create or open a topology** → add nodes/links or use a template → **Deploy**.
3. **Runtime Access** → run **ping** or **HTTP** traffic test → view deployment events.
4. Optional: **Save version** → edit graph → **Rollback**; **Integration outputs** or **IaC export** download.
5. **Destroy** deployment to tear down labeled Docker resources.

Scripted UI/CLI walkthrough: [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) · automated smoke: `./scripts/demo_full_flow.sh`

---

## Deployments

| Environment | Doc | Typical API | SPA |
|-------------|-----|-------------|-----|
| **Local** | [docs/OPERATIONS.md](docs/OPERATIONS.md) | `http://localhost:8000` | `http://localhost:5174` |
| **Staging** | [docs/STAGING_DEPLOYMENT.md](docs/STAGING_DEPLOYMENT.md) | `https://api-staging.cloudnetstudio.com` | Vercel preview / `app-staging` |
| **Production** | [docs/CICD_DEPLOYMENT.md](docs/CICD_DEPLOYMENT.md) | `https://api.cloudnetstudio.com` | Vercel production |

Staging and production deploys are **manual GitHub Actions** workflows; they are operated demos, not multi-tenant production SaaS.

---

## Local run

**Prerequisites:** Python 3.11+, Node 20+, PostgreSQL, Docker Engine (for real deploys).

```bash
# Database (host port 5433)
docker compose up -d postgres
export DATABASE_URL="postgresql://cns_user:cns_password@127.0.0.1:5433/cloud_networking_studio"

# Backend
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

- API docs: http://localhost:8000/docs  
- UI: http://localhost:5174 (Vite proxies `/api` → port 8000)

After schema changes: `docker compose down -v && docker compose up -d --build` if tables are missing. More: [docs/OPERATIONS.md](docs/OPERATIONS.md) · [docs/AUTH.md](docs/AUTH.md)

---

## Why this project

CNS demonstrates skills recruiters and interviewers often look for in platform and networking roles:

- **Model vs runtime separation** — persisted graph intent vs imperative Docker apply
- **Orchestration-shaped APIs** — deploy, destroy, reconcile, heal, event streams
- **Real networking labs** — multi-segment routing, traffic validation, failure injection
- **Production-shaped delivery** — CI, staging/prod workflows, Terraform, smoke tests, CORS/auth hardening

It is intentionally **honest about scope**: one control plane, Docker-first runtime, portfolio deployment — not claiming full multi-region HA or managed Kubernetes as a product.

---

## Documentation

| Doc | Purpose |
|-----|---------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, flows, versioning/profiles |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Local dev, deploy, smoke tests, troubleshooting |
| [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) | Step-by-step demo (UI + CLI) |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Implemented vs planned |
| [docs/AUTH.md](docs/AUTH.md) | Auth, projects, tokens |
| [docs/TOPOLOGY_VERSIONING_AND_PROFILES.md](docs/TOPOLOGY_VERSIONING_AND_PROFILES.md) | Versions, rollback, profiles |
| [docs/TEAM_COLLABORATION.md](docs/TEAM_COLLABORATION.md) | Roles and invitations |
| [docs/CI.md](docs/CI.md) | GitHub Actions CI |

---

## License

No `LICENSE` file in this repository yet; add one before public distribution.
