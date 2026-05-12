# Deployment guide

This document covers **local production-style** deployment with Docker Compose and a practical **EC2** path. For architecture context, see [ARCHITECTURE.md](ARCHITECTURE.md) and the repository [README](../README.md).

---

## What ships in the repo

| Artifact | Purpose |
|----------|---------|
| [docker-compose.prod.yml](../docker-compose.prod.yml) | Postgres + FastAPI + static UI + **Caddy** reverse proxy |
| [backend/Dockerfile](../backend/Dockerfile) | Production API image (`uvicorn`) |
| [frontend/Dockerfile](../frontend/Dockerfile) | Vite production build + **nginx** |
| [deploy/Caddyfile.prod](../deploy/Caddyfile.prod) | Routes `/api/*` → backend, everything else → frontend |

**Defaults:** UI and API are same-origin at `http://localhost` (port **80**). OpenAPI: `http://localhost/api/docs`.

---

## Environment variables

| Variable | Service | Description |
|----------|---------|-------------|
| `DATABASE_URL` | backend | PostgreSQL DSN (required in containers). Compose default points at the `postgres` service. |
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

1. From the repository root, optionally create `.env` (see `.env.example`) to override passwords and ports.

2. Build and start:

   ```bash
   docker compose -f docker-compose.prod.yml up --build -d
   ```

3. Validate compose syntax (also run in CI):

   ```bash
   docker compose -f docker-compose.prod.yml config --quiet
   ```

4. **Verification**

   ```bash
   curl -sf http://localhost/health
   curl -sf http://localhost/api/health
   ```

   Open `http://localhost` in a browser for the dashboard. API docs: `http://localhost/api/docs`.

5. **Real Docker workloads** (deploy, traffic tests, failure injection against the **host** Docker engine):

   Uncomment the `volumes` block under `backend` in `docker-compose.prod.yml`:

   ```yaml
   volumes:
     - /var/run/docker.sock:/var/run/docker.sock
   ```

   Then recreate the backend container. Without the socket, the API runs but **cannot** reach a real Docker engine from inside the container.

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

## EC2 deployment (Docker + Compose)

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

```bash
docker compose -f docker-compose.prod.yml down -v
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
