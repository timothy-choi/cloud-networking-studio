# Contributing

Thank you for helping improve Cloud Networking Studio. This project values **small, reviewable changes**, **tests**, and **documentation** that stays aligned with real behavior.

---

## Ground rules

1. **Do not break** `scripts/demo_full_flow.sh` without updating docs and any tests that pin URLs or behavior.
2. **Preserve public HTTP contracts** unless you are intentionally versioning APIs — prefer additive changes.
3. **Keep Docker runtime provider support** working — it is the primary demo path.
4. **Match existing style:** formatting, typing, and FastAPI patterns already in `backend/app/`.

---

## Workflow

1. **Discuss** larger design shifts via issue or draft PR description (lifecycle changes, provider contracts).
2. **Branch** from `main` with a short descriptive name.
3. **Implement** with focused commits (feat/fix/docs/chore prefixes optional but welcome).
4. **Test** — see [docs/testing.md](docs/testing.md).
5. **Document** user-visible behavior in `README.md` or `docs/` when endpoints or setup change.

---

## Local setup

See **[docs/local-development.md](docs/local-development.md)** for environment variables, Postgres, and running Uvicorn.

---

## Code review checklist

- [ ] Behavior covered by tests where feasible (unit or integration).
- [ ] No unrelated refactors mixed into feature PRs.
- [ ] OpenAPI remains accurate (`/docs` renders cleanly).
- [ ] Secrets never committed; `.env` stays ignored.

---

## Reporting issues

Include: OS, Python version, Docker version, `DATABASE_URL` shape (redact passwords), and minimal reproduction steps or curl transcripts.
