# Deployment guide

This document covers **local production-style** deployment with Docker Compose and a practical **EC2** path. For architecture context, see [ARCHITECTURE.md](ARCHITECTURE.md) and the repository [README](../README.md).

---

## What ships in the repo

| Artifact | Purpose |
|----------|---------|
| [docker-compose.prod.yml](../docker-compose.prod.yml) | Compose **Postgres** (host **5433** for local tools) + FastAPI + static UI + **Caddy** — set **`DATABASE_URL`** for external DB (e.g. [RDS](RDS.md)) |
| [backend/Dockerfile](../backend/Dockerfile) | Production API image (`uvicorn`) |
| [frontend/Dockerfile](../frontend/Dockerfile) | Vite production build + **nginx** |
| [deploy/Caddyfile.prod](../deploy/Caddyfile.prod) | Routes `/api/*` → backend, everything else → frontend |

**Backend ↔ host Docker:** `docker-compose.prod.yml` mounts **`/var/run/docker.sock`** into the `backend` service so `runtime_target: docker` can provision real networks and containers on the **host** engine. That is required for deploy/teardown in production-style runs and for CI’s optional heavy smoke. Removing the mount yields a tighter blast radius but **disables real Docker orchestration** from the API (see [Docker socket and security](#docker-socket-and-security) below).

**Defaults:** UI and API are same-origin at `http://localhost` (port **80**). OpenAPI: `http://localhost/api/docs`.

---

## Docker socket and security

Giving the backend container access to **`/var/run/docker.sock`** is the common pattern for “Docker-out-of-Docker”: the FastAPI process uses the Docker HTTP API over the Unix socket, which is equivalent to granting **root-level control of the host’s Docker engine** to whoever can execute inside that container (and to any code path that can drive the Docker SDK).

**Tradeoffs:**

| With socket mount | Without socket mount |
|-------------------|----------------------|
| Deploy, destroy, runtime inspection, traffic tests, and failure injection work against **real** containers on the host. | API and UI still run; topology CRUD works; **deploy** paths that need the engine will fail or must use a non-Docker runtime. |
| A critical vulnerability in the API (or dependency) could, in the worst case, be leveraged toward **host container escape via Docker** (standard Docker threat model). | Smaller attack surface for the control plane container; align with “read-only API” demos. |

Mitigations in real deployments: keep the API **private** (security groups, mTLS, VPN), run it on a **dedicated** host or VM, **patch** images regularly, restrict **who** can reach `/api`, and consider advanced setups (rootless Docker, remote engine with TLS) if you outgrow single-node Compose.

**CI:** GitHub Actions uses the same compose file, so the optional **heavy** smoke test exercises deploy/destroy against the **runner’s** Docker. See [CI.md](CI.md).

---

## Environment variables

| Variable | Service | Description |
|----------|---------|-------------|
| `DATABASE_URL` | backend | PostgreSQL DSN (required in containers). With bundled Postgres, default points at the `postgres` service; with **AWS RDS**, set the RDS endpoint and credentials (see [RDS.md](RDS.md)). |
| `CNS_ENVIRONMENT` | backend | Shown in `/health` (e.g. `production`). |
| `CNS_CONTROLLER_MODE` | backend | Controller mode string (default `manual`). |
| `CNS_CORS_ORIGINS` | backend | Comma-separated browser origins allowed by CORS (include your public site URL). |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | postgres | Database bootstrap (compose defaults documented in [docker-compose.prod.yml](../docker-compose.prod.yml)). |
| `VITE_API_BASE_URL` | frontend **build** | API base path or URL baked into the static bundle (default `/api` for Caddy). |
| `CADDY_HTTP_PORT` | caddy | Host port published for HTTP (default `80`). |

Copy examples:

- [../.env.example](../.env.example) — compose-level overrides  
- [../backend/.env.example](../backend/.env.example) — local `uvicorn` from `backend/`  
- [../frontend/.env.example](../frontend/.env.example) — Vite dev / optional build overrides  

---

## Local production deployment (Docker Compose)

### Prerequisites

- Docker Engine **24+** and Docker Compose **v2** (`docker compose`).
- Ports **80** (or `CADDY_HTTP_PORT`) free on the host.

### Steps

1. From the repository root, optionally create `.env` (see `.env.example`) to override passwords and ports. For **managed Postgres on AWS**, see [RDS.md](RDS.md).

2. Build and start the stack (Postgres starts automatically; backend waits for DB health):

   ```bash
   docker compose -f docker-compose.prod.yml up --build -d
   ```

3. **Validate** compose syntax (also run in CI before `up`):

   ```bash
   docker compose -f docker-compose.prod.yml config --quiet
   ```

4. **Verification**

   ```bash
   curl -sfI http://localhost/ | head -n 3
   curl -sf http://localhost/api/health
   ```

   (`GET /` is served by the static frontend; the API lives under **`/api/…`** behind Caddy.)

   Open `http://localhost` in a browser for the dashboard. API docs: `http://localhost/api/docs`.

5. **Real Docker workloads** (deploy, traffic tests, failure injection) require the backend to reach the **host** Docker engine. The default `docker-compose.prod.yml` already mounts **`/var/run/docker.sock`** into `backend`. To **disable** real engine access (tighter security, API-only), remove the `volumes` entry under `backend` and recreate the container.

6. **Logs**

   ```bash
   docker compose -f docker-compose.prod.yml logs -f backend
   docker compose -f docker-compose.prod.yml logs -f caddy
   ```

7. **Stop / remove**

   ```bash
   docker compose -f docker-compose.prod.yml down
   # Remove DB volume as well (destructive):
   docker compose -f docker-compose.prod.yml down -v
   ```

---

## Continuous integration (GitHub Actions)

On every push to `main` and on pull requests, CI runs **pytest**, a **production `npm run build`**, then **`docker compose -f docker-compose.prod.yml up -d --build`** on an `ubuntu-latest` runner with **`AUTH_REQUIRE_LOGIN=true`** and a strong ephemeral **`AUTH_SECRET_KEY`** (Step 53D rejects the compose dev default in production), waits for HTTP readiness (up to 90 seconds), and runs **`scripts/prod_smoke_test.sh`** with **`CNS_HEAVY_SMOKE=1`** so **deploy + destroy** is exercised against the runner’s Docker engine (same socket mount as production compose). The smoke script **registers** a unique user, obtains a **JWT**, creates a topology under a **project**, and asserts **401** for unauthenticated topology **POST**.

Details, log capture on failure, and what is **not** covered: [CI.md](CI.md).

---

## EC2 deployment (Docker + Compose)

**Step-by-step commands** (launch instance, install Docker, clone, `.env`, compose, logs, health, cleanup): [EC2_RUNBOOK.md](EC2_RUNBOOK.md).

### 1. Instance sizing (starting point)

- **t3.small** or larger for API + Postgres + UI on one instance.  
- Allocate enough disk for Docker images and Postgres data (20+ GB recommended).

### 2. Install Docker

Use the official Docker **Engine** install guide for your AMI (Amazon Linux 2023, Ubuntu, etc.). Verify:

```bash
docker version
docker compose version
```

### 3. Clone and configure

```bash
sudo mkdir -p /opt/cns && sudo chown "$USER:$USER" /opt/cns
cd /opt/cns
git clone <your-repo-url> cloud-networking-studio
cd cloud-networking-studio
cp .env.example .env
```

Edit `.env`: set a **strong** `POSTGRES_PASSWORD`, align `DATABASE_URL` if you change credentials, set `CNS_CORS_ORIGINS` to your **public origin** (e.g. `http://ec2-1-2-3-4.compute.amazonaws.com`), and adjust `VITE_API_BASE_URL` only if you rebuild the frontend with a different API URL.

### 4. Open security group ports

- **80** (and **443** if you terminate TLS on the instance) inbound. Restrict source IPs in real production.

### 5. Start the stack

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

For **AWS RDS**, set **`DATABASE_URL`** in **`.env`** to your RDS DSN (the API uses it; the Compose `postgres` service may still run unused on the host — see [RDS.md](RDS.md)).

### 6. Restart after code updates

```bash
cd /opt/cns/cloud-networking-studio
git pull
docker compose -f docker-compose.prod.yml up --build -d
```

### 7. Logs and debugging

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=200 backend postgres caddy
```

Exec into Postgres if needed:

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  psql -U cns_user -d cloud_networking_studio
```

### 8. Cleanup on EC2

**HTTP-only** stack (no **`docker-compose.caddy-https.yml`**): **`down -v`** removes containers and the **`postgres_data`** volume (destructive).

```bash
docker compose -f docker-compose.prod.yml down -v
```

**Production HTTPS** (merge **`docker-compose.caddy-https.yml`**, **`CNS_CADDY_AUTO_HTTPS=on`**): **do not** run **`down -v`**. It deletes Compose volumes **`caddy_data`** and **`caddy_config`**, where Caddy stores **Let's Encrypt** state; the next **`up`** re-requests certificates and can hit **rate limits**. Use **`docker compose … down`** (no **`-v`**) for routine restarts, or remove **only** the Postgres volume by name if you must reset the database.

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.caddy-https.yml --env-file .env down
```

---

## CNS / Docker cleanup (development host)

Label-scoped resources are created when you **deploy** topologies. Use the API to **destroy** deployments, or inspect Docker:

```bash
docker ps -a --filter "label=cns"
docker network ls --filter "label=cns"
```

Avoid blind `docker system prune -af` on shared machines.

---

## Troubleshooting

### Docker permission denied (`/var/run/docker.sock`)

Add your user to the `docker` group and re-login, or run compose with appropriate permissions. On EC2, use a user in `docker`.

### Port 80 already in use

Set `CADDY_HTTP_PORT=8080` in `.env` and browse `http://localhost:8080`.

### CORS errors in the browser

Ensure `CNS_CORS_ORIGINS` includes the **exact** origin the user types (scheme + host + port), e.g. `http://127.0.0.1` vs `http://localhost`.

### Frontend cannot reach API

Behind Caddy, the UI should call **`/api`** (default production build). If you host the SPA separately from the API, rebuild the frontend with `VITE_API_BASE_URL` pointing at the full API URL.

### Postgres connection refused from backend

Wait for `postgres` healthcheck to pass; verify `DATABASE_URL` host is `postgres` inside compose, not `localhost`.

### `docker compose config` fails

Check YAML indentation and that `deploy/Caddyfile.prod` exists relative to the compose file.

---

## What is *not* included (before public internet hosting)

- **TLS certificates** for HTTPS on port 443 (use Caddy/Let’s Encrypt, AWS ACM on ALB, or Cloudflare).  
- **Secrets management** (AWS Secrets Manager, SSM, Vault) — compose uses env files today.  
- **High availability** (multi-AZ Postgres, replicated API, load balancers).  
- **Rate limiting, authn/authz**, and **WAF** in front of the API.  
- **Managed RDS** instead of container Postgres for durability.  
- **Alembic migrations** — tables are created via `create_all` at startup; Alembic is a natural next step.

---

## Recommended next infrastructure steps

1. Put an **ALB** or **Cloudflare** in front; terminate TLS there or on Caddy.  
2. Move Postgres to **RDS** (or managed equivalent) and point `DATABASE_URL`.  
3. Add **GitHub OIDC** → AWS for push-to-deploy instead of manual `git pull` on EC2.  
4. Add **structured logging**, metrics, and **health checks** wired to autoscaling groups.  
5. Introduce **Alembic** migrations and remove reliance on `create_all` in production.
