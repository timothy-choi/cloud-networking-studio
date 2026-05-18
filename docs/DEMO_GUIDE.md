# Cloud Networking Studio — 5-minute demo guide

This script is for recruiters, interviewers, or new teammates. You can run everything in **Docker mode** on a laptop; **Kubernetes** is optional and only needed when you want to show cluster-backed labs.

## Before you start

- Bring up the stack (see repository **README** quickstart): API, Postgres, frontend, and the **Go runtime executor** when you plan to show live deploys, Runtime Access, and in-network checks.
- Log in or register — registration creates a starter **project** automatically.
- Optional: open **Dashboard** and use **Start demo (optional)** to create the `CNS Quick demo` project, clone the built-in `client-service` template, deploy, and jump to the topology page in one action.

## 5-minute narrative (UI)

1. **Projects (30s)** — Explain that every topology and deployment is scoped to a project for RBAC. Switch the project selector or create a new workspace.
2. **Topology builder (60s)** — Open a topology. Point out **nodes** (hosts, services, routers), **links** (L2/L3 intent), and the **canvas** vs inspector. Mention **templates** as reusable snapshots.
3. **Deploy (45s)** — Click **Deploy to runtime**. Walk the deployment timeline and events; clarify that this is the control plane talking to Docker or Kubernetes via the executor.
4. **Runtime Access (90s)** — Open tabs: **Endpoints** for internal URLs, **Services** for **Expose / Unexpose** (publish ports without implying insecure defaults), and **Instructions** for copy-paste snippets.
5. **Runtime operations (60s)** — From Runtime Access or the topology page: **logs**, **health check**, **traffic test**, **safe exec**, **restart**. Emphasize *safe exec* is allowlisted diagnostics, not arbitrary shells.
6. **Destroy (30s)** — Tear down the deployment when finished; mention this frees provider resources and is part of the guided checklist.

Total ≈ 5 minutes with questions; skip **Expose** or **safe exec** if time is tight.

## Docker mode demo

- Set topology **runtime target** to **docker** (default for starters).
- Show **bridge** networking and container names in Runtime Access.
- Run a **ping** or **HTTP traffic test** between nodes after deploy.
- If the executor is unavailable, say honestly that operations fall back or degrade — see **Troubleshooting** below.

## Kubernetes mode demo

- Switch topology **runtime target** to **kubernetes** (if your environment is wired for it).
- Highlight **namespace / workload** mapping in Runtime Access and that **in-cluster** probes require the Go runner.
- Prefer a pre-tested template (e.g. gateway → API → DB) if your cluster has pull secrets and storage class configured.

## CLI / API tokens demo (90s)

1. Open **API tokens**, create a token, copy it once.
2. From the repo: `python3 -m cli.cns --help` (or your packaged CLI) with `CNS_BASE_URL` pointing at the API.
3. Show **project list** and **deploy** commands mirroring the UI — same RBAC as the browser.

## What to highlight for recruiters / interviewers

- **Intent vs runtime**: Topologies are desired state; deployments are concrete runs with audit events.
- **Safe operations**: Distinct paths for **expose**, **health**, **traffic tests**, and **safe exec** vs destructive failure injection labs.
- **Multi-tenant projects**: Membership roles and API tokens reuse the same access control.
- **Production polish**: Health endpoints, metrics summary, and optional HTTPS compose overlays (see **README**).

## Troubleshooting (common)

| Symptom | Likely cause | What to try |
|--------|----------------|-------------|
| Deploy stays pending / fails immediately | Executor not reachable, or validation on nodes/links | Check `GET /runtime/status`, fix missing images/IPs, read deployment events. |
| Runtime Access empty | Deploy not succeeded or runner did not return metadata | Confirm deployment status **succeeded**; verify `RUNTIME_EXECUTOR=go` for rich payloads. |
| Health check “unsupported” on Kubernetes | Control plane cannot reach pod ClusterIP | Use Go runner in-cluster probes (see runtime docs). |
| Duplicate deploy 409 | Active deployment still exists | **Destroy** the deployment, then deploy again. |
| Onboarding steps stuck | Auto-detect needs matching data | Use **Mark done** on the checklist, or perform the action (e.g. run a succeeded traffic test for the health step heuristic). |

## Reset onboarding (testing)

- `POST /onboarding/reset` clears manual checklist progress for the current user (requires auth).

## Screenshot / GIF placeholders

Drop assets under `docs/media/` (not committed here) and link from the main **README** when you have:

- `dashboard-onboarding.png` — checklist + **Start demo** card.
- `topology-runtime-access.png` — Services tab with expose controls.
- `cli-token-flow.gif` — token create + `cns` command.
