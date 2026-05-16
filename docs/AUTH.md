# Authentication and multi-tenant projects

Cloud Networking Studio uses **JWT access tokens** (HS256) and **bcrypt** password hashes (via **passlib**). Topologies belong to **projects**, and projects belong to **users**. Mutating and data APIs require an authenticated user; **`GET /health`** stays public.

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| **`AUTH_SECRET_KEY`** | **Yes in production** | Symmetric key for signing JWTs. Use a long random string (at least 32 characters). The repo ships a **development default** so local runs work without copying secrets. |
| **`AUTH_TOKEN_EXPIRE_MINUTES`** | No | Access token lifetime in minutes (default from settings, typically **60**). |
| **`AUTH_REQUIRE_LOGIN`** | No | If **`true`**, data and mutating APIs require **`Authorization: Bearer <token>`**. If **`false`** (default for local dev), those routes can use an implicit **bootstrap dev user** for ownership and scripts. **`GET /auth/me` always requires a Bearer JWT** regardless of this flag. |

Set these in **`backend/.env`** (when running uvicorn from `backend/`) or in your process manager / container environment. See [backend/.env.example](../backend/.env.example).

---

## API overview

| Method | Path | Notes |
|--------|------|--------|
| `POST` | `/auth/register` | Creates **user** + default **project** (“My workspace”), returns **`access_token`** + **`user`**. Password: **8–72 UTF-8 bytes** (bcrypt); longer values return **400** with a clear message (emoji-heavy passwords can exceed the byte limit before the character count). |
| `POST` | `/auth/login` | Returns **`access_token`** + **`user`**. |
| `GET` | `/auth/me` | **Always** requires **`Authorization: Bearer <token>`** (returns **401** without it). Never returns the implicit dev user. |
| `POST` | `/auth/logout` | **204** — stateless JWT; clients discard the token. |
| `GET` | `/projects` | List projects you own. |
| `POST` | `/projects` | Create a project. |
| `GET` | `/topologies?project_id=<uuid>` | List topologies in that project (must be yours). |

`hash_password` / `verify_password` apply the same **SHA-256 pre-hash** when a secret exceeds **72 UTF-8 bytes**, so bcrypt never receives an oversized input; registration still enforces the **72-byte** cap so users do not rely on that path.

Send **`Authorization: Bearer <access_token>`** on protected routes when **`AUTH_REQUIRE_LOGIN=true`**, and whenever you want to act as a specific registered user in dev.

### Browser session (logout and stuck state)

- **Log out** (header on authenticated pages) calls **`POST /auth/logout`** when possible, then always clears **`sessionStorage`** (JWT + selected project) and sends you to **`/login`**. The SPA only loads your profile when a token is present and **`GET /auth/me`** succeeds.
- **Clear stored session** on the sign-in / register screens drops the same keys without calling the server (useful if a token is invalid or the API changed).
- Open **`/login?reset=1`** (or register with the same query) to auto-clear on load once.

---

## Database volumes after auth / schema changes

The API runs ``SQLAlchemy`` ``create_all()`` on startup and checks that core tables exist (**``users``**, **``projects``**, **``topologies``** with **``project_id``**). If Postgres was created from an older image or ORM layout, you can still have a **healthy empty data directory** that never received the new DDL, or mismatched objects, which surfaces as errors like ``relation "users" does not exist``.

**Do not rely on old DB volumes silently.** After auth or project/topology model changes, reset the local database volume and rebuild:

```bash
docker compose down -v
docker compose up -d --build
```

Use the same pattern with **``docker compose -f docker-compose.prod.yml …``** when you develop against the production-style stack.

---

## Production smoke (`scripts/prod_smoke_test.sh`)

CI, EC2 deploy, and ephemeral PR stacks run this script against the public base URL (paths under **`/api/…`** through Caddy). After **Step 34** it:

1. Waits for edge readiness: **full-stack** (EC2/sslip) **`GET /`** and **`GET /api/health`**; with **`CNS_SMOKE_API_ONLY=1`** (production **`deploy-production.yml`**) only **`GET /api/health`** because the API host has no SPA (app is on **Vercel**). Base URL is **`https://api.cloudnetstudio.com`** by default (or **`CNS_PRODUCTION_API_HOST`**), without **`-L`**. Tunable **`CNS_CURL_*`** and inner retries help slow DNS.
2. Asserts **`POST /api/topologies`** **without** `Authorization` returns **401** (requires **`AUTH_REQUIRE_LOGIN=true`** on the backend, as in CI and recommended production **`.env`**).
3. **Registers** via **`POST /api/auth/register`** as `smoke+<timestamp>@example.com` (or **logs in** on **409** duplicate), stores **`access_token`**, then creates a topology under a **project** using **`Authorization: Bearer …`**.

Set **`AUTH_SMOKE=0`** for health-only checks (no JWT / topology). See [CI.md](CI.md) and [EC2_RUNBOOK.md](EC2_RUNBOOK.md).

---

## Local development

1. Start Postgres (`docker compose up -d postgres` or `docker compose -f docker-compose.prod.yml up -d postgres`) and the API as in the [README](../README.md#quickstart).
2. **Web UI:** register or sign in so the SPA stores a JWT in **`sessionStorage`** (`cns_access_token`). The app does **not** call **`GET /auth/me`** until a token exists, so you are not treated as the backend dev user in the browser.
3. **`curl` / scripts** with **`AUTH_REQUIRE_LOGIN=false`**: most routes still accept unauthenticated calls and attribute them to the implicit dev user for data ownership; use **`Authorization: Bearer …`** when you want a specific registered user. **`GET /auth/me`** still needs a Bearer token.
4. Set **`AUTH_REQUIRE_LOGIN=true`** in production so anonymous clients cannot hit data APIs without a JWT; pair with a strong **`AUTH_SECRET_KEY`**.

### curl examples

Register and call a protected route:

```bash
API=http://127.0.0.1:8000
TOKEN=$(curl -s -X POST "$API/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"hunter2hunter2","display_name":"You"}' \
  | jq -r .access_token)

curl -s "$API/auth/me" -H "Authorization: Bearer $TOKEN" | jq .
curl -s "$API/projects" -H "Authorization: Bearer $TOKEN" | jq .
```

---

## Production secret setup

1. Generate a strong secret, for example: `openssl rand -hex 32`.
2. Set **`AUTH_SECRET_KEY`** in your deployment environment (never commit real values). Rotate by issuing new tokens after key rotation (there is no refresh token in this stack — keep expiry reasonable with **`AUTH_TOKEN_EXPIRE_MINUTES`**).
3. Set **`AUTH_REQUIRE_LOGIN=true`** so anonymous clients cannot use the implicit dev user on **data APIs** (they still receive **401** on **`GET /auth/me`** without a Bearer token in all modes).
4. Ensure HTTPS terminates in front of the API or reverse proxy so tokens are not sent in clear text.

---

## Authorization behavior

- **401** — Missing or invalid JWT (including **`GET /auth/me`** without **`Authorization: Bearer`**), invalid credentials on login, or protected routes when **`AUTH_REQUIRE_LOGIN=true`**.
- **404** — Topology, deployment, or other resource not found **or** not owned by your projects (avoid leaking existence of other tenants’ IDs).

Existing **deploy**, **destroy**, **traffic**, **failure**, **reconcile**, and **heal** flows are unchanged; they operate on resources that pass the same ownership checks.

---

## Frontend

The dashboard is behind **`RequireSession`**, which only considers you signed in when a JWT is stored and **`GET /auth/me`** succeeds with that Bearer token. With no token, the SPA shows **`/login`** and does not probe **`/auth/me`**. The **project** selector scopes the topology list; **New project** and topology create actions use the selected project.
