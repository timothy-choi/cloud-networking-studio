# Production readiness

High-level checklist for operating Cloud Networking Studio outside local development.

## Environment variables

- **`DATABASE_URL`** — persistent Postgres (managed RDS or similar). The default local URL is not suitable for production.
- **`AUTH_SECRET_KEY`** — long random secret (minimum length enforced by the app). Never commit real values.
- **`AUTH_REQUIRE_LOGIN`** — set `true` so APIs require Bearer JWTs (except documented public routes).
- **`CNS_CORS_ORIGINS`** / **`CNS_CORS_ORIGIN_REGEX`** — include your real browser origin(s).
- **`RUNTIME_EXECUTOR`** — `python` (Docker SDK in API) or `go` (delegate to `cns-runner`).
- **`GO_RUNNER_URL`** — reachable from the API container when using `RUNTIME_EXECUTOR=go`.
- **`CNS_BASE_URL`** — used by the CLI and CI when pointing at your public API (e.g. `https://api.example.com/api`).

## API domain and Caddy

- Terminate TLS at Caddy/nginx and reverse-proxy `/api/*` to the FastAPI service with the `/api` prefix stripped as documented in your `Caddyfile`.
- Keep the SPA and API on the same site where possible so the UI can use same-origin `/api`.

## Auth

- Rotate **`AUTH_SECRET_KEY`** on any suspicion of compromise.
- Prefer short-lived JWTs and personal **API tokens** for automation (`POST /api-tokens`).

## Database persistence

- Run Postgres with durable storage and backups.
- Migrations/schema updates should be applied through your normal release process.

## Runner security

- The Go runner performs privileged runtime operations; restrict network access (internal VPC only), authenticate callers if you expose it beyond the control plane, and patch images regularly.

## Docker socket warning

- **`RUNTIME_EXECUTOR=python`** with real Docker gives the API process access to the Docker socket — equivalent to root on the host. Prefer isolating the API on dedicated nodes or using the runner pattern with tight network policy.

## Kubernetes kubeconfig warning

- Mounting kubeconfig or in-cluster credentials into the runner grants cluster-admin-level capabilities depending on RBAC. Scope service accounts to namespaces and verbs required for lab deployments only.

## Limitations / future work

- Segmented multinet on the Go runner is not yet at parity with the Python executor (see runner errors when `segmented_networks` is true).
- Subnet overlap handling prefers alternate `/24` ranges when the topology supplies a colliding `/24`; unusual prefix lengths may still fail fast with a clear error.
- Platform status from the control plane is a best-effort probe — use your own monitoring for SLIs.
