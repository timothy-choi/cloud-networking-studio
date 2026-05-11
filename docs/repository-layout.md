# Repository layout

This repository is organized so the **HTTP API**, **domain logic**, **runtime integrations**, and **automation** stay separate. Physical moves of Python packages are intentionally avoided unless paired with import/test updates; this document describes the **current** production-grade layout.

```
cloud-networking-studio/
├── .github/workflows/     # CI (tests against Postgres service)
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routers (HTTP surface)
│   │   ├── core/          # Settings and configuration
│   │   ├── db/            # Engine, session, Base
│   │   ├── models/        # SQLAlchemy ORM models
│   │   ├── providers/     # Runtime providers (Docker implementation + interfaces)
│   │   ├── schemas/       # Pydantic request/response models (OpenAPI)
│   │   ├── services/      # Deployment planning, runtime, controller, traffic, failures
│   │   └── main.py        # Application factory and router mounting
│   ├── tests/             # Pytest suite
│   └── requirements.txt
├── docs/                  # Architecture and onboarding (you are here)
├── frontend/              # Vite + React + TypeScript dashboard (Tailwind, React Flow)
├── scripts/               # Demo and helper shell scripts (do not break paths casually)
├── docker-compose.yml     # Local Postgres (published port 5433 by default)
└── README.md
```

---

## Where to look for common tasks

| Task | Location |
|------|----------|
| Add/modify HTTP routes | `backend/app/api/` |
| Persist new entities | `backend/app/models/` + migrations if you add Alembic |
| OpenAPI / request bodies | `backend/app/schemas/` |
| Business logic | `backend/app/services/` |
| Docker / provider behavior | `backend/app/providers/` |
| Cross-cutting config | `backend/app/core/config.py` |
| Build dashboard UI | `frontend/` |
| E2E demo | `scripts/demo_full_flow.sh` |

---

## Scripts contract

- **`scripts/demo_full_flow.sh`** is the golden path demo. **Keep `API_BASE` and endpoint paths stable** or update tests and documentation together.
- Cleanup helpers (if present) should remain idempotent and safe for local dev.

---

## Future refactors (optional)

If the codebase grows, common incremental upgrades include:

- **`backend/app/domain/`** — pure domain types free of FastAPI/SQLAlchemy.
- **`backend/app/adapters/`** — rename from `providers/` only when imports are updated systematically.
- **`packages/`** — shared protobuf/OpenAPI clients for a future frontend monorepo.

None of these are required for the current API-first milestone.
