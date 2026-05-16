# Continuous integration

GitHub Actions runs on every push to `main` and on pull requests (see [.github/workflows/ci.yml](../.github/workflows/ci.yml)).

## What runs

| Stage | Purpose |
|--------|---------|
| **Backend (pytest)** | Unit and API tests against a service container Postgres; `CNS_USE_FAKE_DOCKER=1` so tests do not require a Docker engine. |
| **Frontend (production build)** | `npm ci`, `npm run test` (Vitest), and `npm run build` — catches TypeScript, unit, and bundling regressions. |
| **Production stack smoke** | Builds and starts [`docker-compose.prod.yml`](../docker-compose.prod.yml) on the runner, waits with [`scripts/wait_caddy_edge.sh`](../scripts/wait_caddy_edge.sh) / [`scripts/ci_wait_for_stack.sh`](../scripts/ci_wait_for_stack.sh) until **`/`** and **`/api/health`** succeed through Caddy, then runs [`scripts/prod_smoke_test.sh`](../scripts/prod_smoke_test.sh). |

The smoke job proves that **images build**, **Compose wiring works**, **Postgres + API + static UI + Caddy** start together, and core **HTTP API** paths used by the dashboard respond.

## What is covered

- Python test suite and frontend production build.
- End-to-end **process** startup: same images and compose file as local production-style runs.
- Live checks: browser bundle served at `/`, API health at `/api/health`, topology **create** (draft) and **list** via `/api/topologies`.

## What is not covered

- **Browser / Playwright** automation — only HTTP-level checks.
- **TLS**, external DNS, and cloud load balancers.
- **Long-running** traffic tests, failure injection, or multi-topology load — kept out of CI for speed and flakiness.
- **Managed Postgres** (RDS, etc.) — CI uses the compose `postgres` service only.
- **Alembic migrations** — the app still uses `create_all` at startup; migration correctness is not exercised in CI.

## Optional heavy smoke

When `CNS_HEAVY_SMOKE=1` is set (enabled in CI on `ubuntu-latest`), [`scripts/prod_smoke_test.sh`](../scripts/prod_smoke_test.sh) also builds a tiny two-node topology, **deploys** against the runner’s Docker engine (backend mounts `/var/run/docker.sock`), waits for deployment success, then **destroys**. This depends on Docker-in-CI behavior and image pulls; it is slower and can fail on registry or engine quirks.

## Local parity

Local development remains **`uvicorn` + Vite** (see [local-development.md](local-development.md)). CI does **not** replace a local dev server; it adds a **production compose** gate so regressions in Dockerfiles, Caddy routing, or container health cannot slip through unnoticed.
