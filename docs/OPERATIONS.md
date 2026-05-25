# Operations

Runbooks for local development, staging/production deploys, smoke tests, and common failures.

---

## Local development

### Prerequisites

- Python 3.11+ (CI uses 3.12)
- Node.js 20+ (CI uses 22)
- PostgreSQL
- Docker Engine (real deploys, traffic, failures)
- `curl`, `jq` (scripts)

### Start stack

```bash
# Postgres on host port 5433
docker compose up -d postgres
export DATABASE_URL="postgresql://cns_user:cns_password@127.0.0.1:5433/cloud_networking_studio"

# Migrations (when using Alembic on a persistent DB)
cd backend && alembic upgrade head

# Backend
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend && npm install && npm run dev
```

- UI: http://localhost:5174  
- API: http://localhost:8000/docs  
- Health: `curl -s http://localhost:8000/health | jq`

### Auth locally

Copy `backend/.env.example` → `backend/.env`. See [AUTH.md](AUTH.md):

- `AUTH_REQUIRE_LOGIN=false` — implicit dev user for quick `curl` (not for staging/prod)
- `AUTH_REQUIRE_LOGIN=true` — register/login; JWT on all protected routes

### Reset database volume

After auth/topology schema changes, stale Postgres volumes cause missing-table errors:

```bash
docker compose down -v
docker compose up -d --build
cd backend && alembic upgrade head   # if using migrations
```

### Tests

```bash
cd backend
export CNS_USE_FAKE_DOCKER=1
pytest tests/ -q

cd frontend
npm run test && npm run build
```

See [testing.md](testing.md) · [CI.md](CI.md)

### Full-stack local (Compose prod file)

```bash
cp .env.example .env   # edit secrets
docker compose -f docker-compose.prod.yml up -d --build
./scripts/prod_smoke_test.sh
```

---

## Staging deploy

**Workflow:** `.github/workflows/deploy-staging.yml` (manual, any branch)

**Doc:** [STAGING_DEPLOYMENT.md](STAGING_DEPLOYMENT.md)

1. Provision staging EC2 (Terraform variable `CNS_STAGING_TERRAFORM_ENABLED` or secret `CNS_STAGING_EC2_HOST`).
2. DNS: `api-staging` → staging EIP (Cloudflare **DNS only**).
3. GitHub → **Actions → Deploy staging → Run workflow** (pick branch).
4. Verify:

```bash
curl -s https://api-staging.cloudnetstudio.com/api/health | jq .environment
# expect "staging"
```

5. Optional heavy smoke (deploy + destroy on instance):

```bash
CNS_BASE_URL=https://api-staging.cloudnetstudio.com \
CNS_SMOKE_API_ONLY=1 \
CNS_HEAVY_SMOKE=1 \
./scripts/prod_smoke_test.sh
```

Staging uses **`STAGING_AUTH_SECRET_KEY`** and isolated compose project **`cns-staging`** — not production secrets.

---

## Production deploy

**Workflow:** `.github/workflows/deploy-production.yml` (manual only)

**Doc:** [CICD_DEPLOYMENT.md](CICD_DEPLOYMENT.md) · [EC2_RUNBOOK.md](EC2_RUNBOOK.md)

1. Configure GitHub secrets (AWS, `AUTH_SECRET_KEY`, `DATABASE_URL` or RDS, Vercel token, etc.).
2. Run **Deploy production** workflow.
3. Workflow: Terraform apply (persistent state) → SSH deploy → Caddy HTTPS → Vercel build with `VITE_API_BASE_URL` → smoke test.

Verify:

```bash
curl -s https://api.cloudnetstudio.com/api/health | jq
curl -s https://api.cloudnetstudio.com/api/runtime/status | jq
```

Production smoke (API-only — SPA on Vercel):

```bash
CNS_BASE_URL=https://api.cloudnetstudio.com \
CNS_SMOKE_API_ONLY=1 \
CNS_EXPECT_ENVIRONMENT=production \
./scripts/prod_smoke_test.sh
```

**Does not** run `terraform destroy` on production.

---

## Smoke test commands

| Script | Purpose |
|--------|---------|
| `./scripts/demo_full_flow.sh` | Local API flat + routed lab (needs Docker) |
| `./scripts/prod_smoke_test.sh` | Health, auth, topology CRUD; optional heavy deploy/destroy |
| `./scripts/wait_caddy_edge.sh` | Edge wait helper used by prod smoke |

**Prod smoke env vars:**

| Variable | Meaning |
|----------|---------|
| `CNS_BASE_URL` | Target host (default `http://127.0.0.1`) |
| `CNS_SMOKE_API_ONLY=1` | Skip SPA `GET /`; only `/api/health` |
| `CNS_HEAVY_SMOKE=1` | Deploy + destroy one topology |
| `AUTH_SMOKE=0` | Health only, skip JWT checks |
| `CNS_EXPECT_ENVIRONMENT` | Assert health JSON `.environment` |

---

## Troubleshooting

### Vercel SPA 404 on refresh

**Symptom:** Direct navigation to `/dashboard` or `/topologies/...` returns 404 on Vercel.

**Cause:** SPA client-side routes need a fallback to `index.html`.

**Fix:** Configure Vercel rewrites (see `vercel.json` in repo if present) so all non-API paths serve the SPA entry.

---

### CORS errors in browser

**Symptom:** Browser blocks API calls; preflight fails or `Access-Control-Allow-Origin` missing.

**Checks:**

1. `VITE_API_BASE_URL` on Vercel build must match the API origin (e.g. `https://api.cloudnetstudio.com/api`).
2. Backend `CNS_CORS_ORIGINS` must include the SPA origin (staging workflow merges `app-staging` + Vercel preview regex).
3. Staging uses `.env.staging` on EC2 — recreate backend container after env changes.

See [STAGING_DEPLOYMENT.md](STAGING_DEPLOYMENT.md) · [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

---

### Backend 500 on metrics or runtime

**Symptom:** `GET /projects/{id}/metrics` or `GET /topologies/{id}/runtime` returns 500.

**Common causes:**

1. **Enum mismatch** — DB has uppercase legacy values (`STOPPED`, `NONE`) while ORM expects lowercase (`stopped`, `none`).
   - **Fix:** `cd backend && alembic upgrade head` (migrations `20260528_*`, `20260529_*`).
   - Code uses coerced string enums in `app/db/coerced_enum.py`.

2. **Missing migration columns** — e.g. `topology_sync_status`, `cleanup_status` not applied.
   - **Fix:** `alembic upgrade head`; check logs for `UndefinedColumn`.

3. **Docker unavailable** — runtime inspection degraded; should return 200 with warning (recent fixes). Check `GET /api/runtime/status`.

---

### Enum migration mismatch (detailed)

**Error examples:**

```text
LookupError: 'STOPPED' is not among the defined enum values
LookupError: 'none' is not among the defined enum values
```

**Fix:**

```bash
cd backend
alembic upgrade head
# restart API containers
docker compose -f docker-compose.prod.yml restart backend
```

Migrations normalize existing rows to lowercase. Application code coerces legacy uppercase on read as a safety net.

---

### Docker / cloud-init failure on EC2

**Symptom:** `cloud-init status` error; Docker missing; apt malformed `docker.list`.

**Cause:** Bad `user_data` heredoc / Terraform `templatefile` escaping (see [TROUBLESHOOTING.md](TROUBLESHOOTING.md)).

**Fix:**

- Replace EC2 instance so fixed `user_data` runs, **or**
- SSH and run `scripts/ec2_bootstrap_docker.sh`, **or**
- Manually repair `/etc/apt/sources.list.d/docker.list`

Deploy workflows also curl/bootstrap Docker before app deploy.

---

### DNS / Caddy / Let's Encrypt

**Symptom:** HTTPS fails; certificate errors; API unreachable on custom domain.

**Checks:**

1. Cloudflare **DNS only** (grey cloud) for API A record → EC2 EIP.
2. Ports 80/443 open in security group.
3. `CNS_CADDY_AUTO_HTTPS=on` and correct `CNS_CADDY_SITE_ADDRESS` in prod compose env.
4. Caddy volumes `caddy_data` / `caddy_config` persist certs.

**Smoke without following redirects to wrong host:**

```bash
curl -v --max-time 30 https://api.cloudnetstudio.com/api/health
```

Use `http://<eip>.sslip.io` only for ephemeral CI labs — not production API hostname.

---

### Deploy 500: missing container image

**Symptom:** `POST .../deploy` 500; Docker `no such image`.

**Fix:** Ensure nodes have valid `image` (e.g. `nginx:alpine`, `alpine:latest`). Backend applies defaults for legacy null images; blank explicit images return 400. Smoke test sets explicit images in heavy mode.

---

## Related docs

| Doc | Topic |
|-----|--------|
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Docker list / cloud-init detail |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Compose prod layout |
| [RDS.md](RDS.md) | Managed Postgres |
| [EPHEMERAL_CI_ENVIRONMENTS.md](EPHEMERAL_CI_ENVIRONMENTS.md) | PR ephemeral stacks |
