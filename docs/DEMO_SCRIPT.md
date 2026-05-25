# Demo script (~10 min)

Repeatable walkthrough for recruiters and interviewers. Automated equivalent: [`scripts/demo_full_flow.sh`](../scripts/demo_full_flow.sh) (flat + routed labs; no versioning UI).

**Prerequisites:** Postgres, backend (`uvicorn`), Docker Engine, frontend (`npm run dev`). API at `http://localhost:8000`, UI at `http://localhost:5174`.

---

## Core flow (UI)

| Step | Action | Proves |
|------|--------|--------|
| 1 | **Register / login** at `/register` or `/login` | Auth; starter project created on register |
| 2 | **Create project** (project selector on dashboard) or use starter project | Project scoping + RBAC |
| 3 | **Create topology** — blank or from **Templates** | Topology CRUD |
| 4 | **Studio** — add **Host**, **Router**, **Service** nodes; connect **links**; set CIDR/gateway if needed; **Save layout** | Graph persisted (nodes, links, positions) |
| 5 | **Deploy to runtime** — watch deployment events | Control plane → Docker apply |
| 6 | **Runtime Access** — endpoints, networks/interfaces, container status | Live inspection vs saved intent |
| 7 | **Traffic** — Run ping / HTTP test | Exec-based data-plane validation |
| 8 | **Failure** — stop or restart a node; optional **Reconcile** → **Heal** | Drift detection and recovery |
| 9 | **Integration outputs** — Runtime Access → **Use outside CNS**; copy or download env/CI files | Deployment-scoped integration artifacts |
| 10 | **IaC export** — topology page → **IaC Export** panel; preview or download Terraform/Ansible/Compose | Topology-scoped IaC generation (export only) |
| 11 | **Save version** — **Versions** panel → save snapshot (manual or after deploy) | Immutable topology history |
| 12 | Edit graph → **Rollback** to prior version (choose mode if prompted) | Version restore; optional destroy before rollback |
| 13 | **Deployment profile** — create profile (env/image overrides) → **Deploy** with profile selected | Effective config merge at deploy time |
| 14 | **Destroy** deployment | Labeled Docker teardown |

**One-liner for deploy:** “We compile the graph into a plan and materialize Docker networks and containers.”

---

## Quick flat lab (5 min)

Skip routing if time is short:

1. Blank topology → Host + Service on one link → Deploy  
2. Ping + HTTP → Stop service → Heal → Destroy  

Template shortcut: dashboard **Start demo (optional)** clones `client-service` and deploys.

---

## Routed lab (optional +5 min)

1. Empty topology → **Use template** → **Routed host → router → service**  
2. Deploy → inspect router interfaces on two segments (`net-a` / `net-b`)  
3. **Run routed ping/HTTP** → restart router → reconcile/heal → destroy  

CLI: second half of `./scripts/demo_full_flow.sh` automates `10.72.0.0/24` / `10.73.0.0/24` labs.

---

## CLI smoke (no UI)

```bash
chmod +x scripts/demo_full_flow.sh
API_BASE=http://127.0.0.1:8000 ./scripts/demo_full_flow.sh
```

Production/staging API-only:

```bash
CNS_BASE_URL=https://api-staging.cloudnetstudio.com \
CNS_SMOKE_API_ONLY=1 \
./scripts/prod_smoke_test.sh
```

---

## Troubleshooting

| Issue | Check |
|-------|--------|
| Empty UI / 502 | Backend running; Vite proxy to port 8000 |
| Deploy fails | Docker running; deployment events JSON; node `image` set |
| Traffic fails | Containers running; HTTP target listens on expected port |
| Auth errors | `AUTH_REQUIRE_LOGIN` and JWT on protected routes |

See [OPERATIONS.md](OPERATIONS.md) · [local-development.md](local-development.md)
