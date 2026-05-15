# Local development

Run the API and optional Postgres locally. Paths assume repository root unless noted.

---

## Requirements

- **Python 3.11+**
- **PostgreSQL 14+** (16 recommended — matches CI compose image)
- **Docker Engine** + **Docker Compose V2** for the bundled Postgres service and runtime demos

Optional:

- **`curl`** and **`jq`** — demo script

---

## Environment variables

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | SQLAlchemy URL for Postgres (overrides default in `app.core.config.Settings`) |
| `ENVIRONMENT` | Logical environment name surfaced on `/health` |
| `CNS_CONTROLLER_MODE` | Controller behavior flag (`manual` default — see code for semantics) |

Example:

```bash
export DATABASE_URL="postgresql://cns_user:cns_password@localhost:5433/cloud_networking_studio"
```

You may also place variables in `backend/.env` (loaded by Pydantic settings).

---

## Start Postgres (recommended)

```bash
docker compose up -d postgres
```

Default compose publishes Postgres on host port **5433** → container **5432**.

---

## Install backend dependencies

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## Run the API

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Interactive docs: **http://localhost:8000/docs**
- Health: **http://localhost:8000/health**

---

## Run the full demo

Requires API running; Docker strongly recommended for runtime-dependent steps.

```bash
# from repo root
./scripts/demo_full_flow.sh
```

Override URL:

```bash
API_BASE=http://127.0.0.1:8000 ./scripts/demo_full_flow.sh
```

---

## CI vs this flow

GitHub Actions still runs **`uvicorn` + Vite** only inside the pytest and npm jobs. A **separate** job builds and starts [`docker-compose.prod.yml`](../docker-compose.prod.yml) with **`--profile localdb`** on the runner to prove the **containerized** stack starts; that does not change how you work locally. See [CI.md](CI.md).

---

## Troubleshooting

### Cannot connect to Postgres

- Confirm container is healthy: `docker compose ps`
- Verify port **5433** is free or change mapping + `DATABASE_URL`
- Check credentials match `docker-compose.yml`

### Docker operations fail from the API

- Ensure Docker daemon is running **on the same machine as Uvicorn** (typical local setup).
- Confirm current user can talk to Docker (`docker ps`).

### Tables missing / schema errors

The app uses `create_all` at startup for iteration; production deployments should move to **Alembic** migrations when introduced.

### Import errors when running uvicorn

Run commands from the **`backend/`** directory so `app` resolves as the Python package, or set `PYTHONPATH` appropriately.

---

## Next steps

- [testing.md](testing.md)
- [system-architecture.md](system-architecture.md)
