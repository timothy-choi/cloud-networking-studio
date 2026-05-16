# Testing

This document explains how tests are organized and how to run them locally and in CI.

---

## Stack

- **pytest** — discovery under `backend/tests/`
- **PostgreSQL** — GitHub Actions provisions a service container; local runs should target a real Postgres instance for integration fidelity

See [.github/workflows/ci.yml](../.github/workflows/ci.yml) for exact CI commands.

---

## Running tests locally

1. Start Postgres and expose **host port 5433** (either file works; credentials match defaults):

   ```bash
   # Minimal local DB (repo root)
   docker compose up -d postgres
   ```

   Or only the DB from the production-style file:

   ```bash
   docker compose -f docker-compose.prod.yml up -d postgres
   ```

2. **`DATABASE_URL`:** leave unset to use the default in [`backend/tests/conftest.py`](../backend/tests/conftest.py) (`127.0.0.1:5433`, database **`cloud_networking_studio`**), or export a DSN that matches your container.

3. From **`backend/`**:

   ```bash
   pip install -r requirements.txt
   pytest
   ```

### Local Postgres vs RDS

- **Local / CI on your machine:** Postgres listens on **`127.0.0.1:5433`** (mapped from Docker). **`pytest`** uses that URL unless you override **`DATABASE_URL`**.
- **Production RDS:** the running application uses **`DATABASE_URL`** pointing at AWS; that does not change how you run **`pytest`** locally — you still need a reachable Postgres for integration tests unless you skip them.

Optional verbosity:

```bash
pytest -q
pytest backend/tests/test_demo_scripts.py -vv
```

Adjust paths if your shell cwd differs — CI typically runs from `backend/` if configured that way.

---

## What is covered

- **API / service logic** via pytest against real Postgres where integration tests exist.
- **Demo scripts** — tests may assert scripts remain executable and aligned with documented URLs (see `backend/tests/`).

Always run **`pytest`** before merging changes that touch routers, providers, or scripts.

---

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| Connection refused to Postgres | DB not running or wrong port in `DATABASE_URL` |
| Flaky failures | Parallel runs hitting same DB — serialize runs or use isolated databases |
| Docker-dependent tests skipped/failing | Engine not available — ensure Docker is running for integration paths |

---

## Writing new tests

- Prefer **explicit fixtures** for DB sessions where patterns already exist in `backend/tests/`.
- Avoid relying on global mutable Docker state unless isolated per test run.
- When adding endpoints, add at least **smoke coverage** or extend existing integration flows.

---

## Related

- [local-development.md](local-development.md)
- [CONTRIBUTING.md](../CONTRIBUTING.md)
