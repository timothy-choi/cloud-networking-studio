# Authentication and multi-tenant projects

Cloud Networking Studio uses **JWT access tokens** (HS256) and **bcrypt** password hashes (via **passlib**). Topologies belong to **projects**, and projects belong to **users**. Mutating and data APIs require an authenticated user; **`GET /health`** stays public.

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| **`AUTH_SECRET_KEY`** | **Yes in production** | Symmetric key for signing JWTs. Use a long random string (at least 32 characters). The repo ships a **development default** so local runs work without copying secrets. |
| **`AUTH_TOKEN_EXPIRE_MINUTES`** | No | Access token lifetime in minutes (default from settings, typically **60**). |
| **`AUTH_REQUIRE_LOGIN`** | No | If **`true`**, every protected route requires a valid **`Authorization: Bearer <token>`** header. If **`false`** (default in local dev), the API can resolve **`GET /auth/me`** and scoped operations using an implicit **bootstrap dev user** so scripts and tests keep working without a token. |

Set these in **`backend/.env`** (when running uvicorn from `backend/`) or in your process manager / container environment. See [backend/.env.example](../backend/.env.example).

---

## API overview

| Method | Path | Notes |
|--------|------|--------|
| `POST` | `/auth/register` | Creates **user** + default **project** (“My workspace”), returns **`access_token`** + **`user`**. Password: **8–72 UTF-8 bytes** (bcrypt); longer values return **400** with a clear message (emoji-heavy passwords can exceed the byte limit before the character count). |
| `POST` | `/auth/login` | Returns **`access_token`** + **`user`**. |
| `GET` | `/auth/me` | Current user from JWT, or bootstrap dev user when login is not required. |
| `POST` | `/auth/logout` | **204** — stateless JWT; clients discard the token. |
| `GET` | `/projects` | List projects you own. |
| `POST` | `/projects` | Create a project. |
| `GET` | `/topologies?project_id=<uuid>` | List topologies in that project (must be yours). |

`hash_password` / `verify_password` apply the same **SHA-256 pre-hash** when a secret exceeds **72 UTF-8 bytes**, so bcrypt never receives an oversized input; registration still enforces the **72-byte** cap so users do not rely on that path.

Send **`Authorization: Bearer <access_token>`** on protected routes when **`AUTH_REQUIRE_LOGIN=true`**, and whenever you want to act as a specific registered user in dev.

### Browser session (logout and stuck state)

- **Log out** (header on authenticated pages) calls **`POST /auth/logout`** when possible, then always clears **`sessionStorage`** (JWT + selected project) and sends you to **`/login`** — it does **not** re-call **`/auth/me`**, so you are not immediately “re-logged in” as the implicit dev user.
- **Clear stored session** on the sign-in / register screens drops the same keys without calling the server (useful if a token is invalid or the API changed).
- Open **`/login?reset=1`** (or register with the same query) to auto-clear on load once.
- Set **`VITE_AUTH_SKIP_IMPLICIT_ME=true`** in **`frontend/.env`** if the backend never serves an implicit user without a token and you want the SPA to treat “no JWT” as logged out on first paint (skips **`GET /auth/me`** when there is no token).

---

## Local development

1. Start Postgres (`docker compose up -d postgres` or `docker compose -f docker-compose.prod.yml up -d postgres`) and the API as in the [README](../README.md#quickstart).
2. With **`AUTH_REQUIRE_LOGIN=false`** (default), you can open the UI without logging in: **`GET /auth/me`** returns the **bootstrap dev user** and a default project; the dashboard lists **project-scoped** topologies after you pick a project.
3. To exercise strict auth, set **`AUTH_REQUIRE_LOGIN=true`** and **`AUTH_SECRET_KEY`** in `backend/.env`, restart uvicorn, then use **Register** / **Sign in** in the UI (JWT stored in **`sessionStorage`** as `cns_access_token`).

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
3. Set **`AUTH_REQUIRE_LOGIN=true`** so anonymous clients cannot use the bootstrap dev path.
4. Ensure HTTPS terminates in front of the API or reverse proxy so tokens are not sent in clear text.

---

## Authorization behavior

- **401** — Missing or invalid JWT when login is required, or invalid credentials on login.
- **404** — Topology, deployment, or other resource not found **or** not owned by your projects (avoid leaking existence of other tenants’ IDs).

Existing **deploy**, **destroy**, **traffic**, **failure**, **reconcile**, and **heal** flows are unchanged; they operate on resources that pass the same ownership checks.

---

## Frontend

The dashboard is behind **`RequireSession`**: if **`/auth/me`** fails (typical when **`AUTH_REQUIRE_LOGIN=true`** and there is no token), the app redirects to **`/login`**. The **project** selector scopes the topology list; **New project** and topology create actions use the selected project.
