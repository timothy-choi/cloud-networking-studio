# CI/CD integration (Step 44)

Use **personal API tokens** (`POST /api-tokens`) as Bearer credentials in pipelines. They map to your user account and inherit the same **project membership** rules as the web UI (viewer / member / owner).

## Create a token

1. In the app UI, open **API tokens** and create a token (or call `POST /api-tokens` with a JWT from login).
2. Store the plaintext secret once in your CI provider (e.g. GitHub Actions **secret** `CNS_TOKEN`).
3. Set the API base URL your runner can reach (e.g. `https://api.example.com` or internal URL). Use secret `CNS_API_BASE_URL`.

## CLI (`python -m cli.cns`)

From the repository root (with `PYTHONPATH` including the repo root):

```bash
export PYTHONPATH=.
python3 -m cli.cns login --email "$CNS_EMAIL" --password "$CNS_PASSWORD"
python3 -m cli.cns --json projects list
```

Or write a token from the UI:

```bash
echo "$CNS_TOKEN" | python3 -m cli.cns token set
```

Global flags (before or on each subcommand, depending on shell layout — use `--json` on the leaf command for clarity):

- `--json` — structured JSON on stdout  
- `--base-url` — overrides `CNS_API_BASE_URL` and config file  
- `--token` — overrides `CNS_TOKEN` and config file  

Config file default: `~/.config/cns/config.json` (override with `CNS_CONFIG`).

## GitHub Actions example

The workflow below: creates a deployment from a topology, waits until the deployment succeeds, reads runtime metadata to find a service URL hint, runs a trivial check, then **always** destroys the deployment in a `finally`-style post job.

```yaml
name: cns-smoke

on:
  workflow_dispatch:

env:
  CNS_API_BASE_URL: ${{ secrets.CNS_API_BASE_URL }}
  CNS_TOKEN: ${{ secrets.CNS_TOKEN }}
  CNS_TOPOLOGY_ID: ${{ secrets.CNS_TOPOLOGY_ID }}

jobs:
  deploy-and-test:
    runs-on: ubuntu-latest
    outputs:
      deployment_id: ${{ steps.deploy.outputs.deployment_id }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install deps (stdlib CLI only)
        run: |
          python3 -c "import sys; print(sys.version)"

      - id: deploy
        name: Create deployment
        run: |
          export PYTHONPATH="${{ github.workspace }}"
          OUT=$(python3 -m cli.cns --json deploy --topology-id "$CNS_TOPOLOGY_ID")
          echo "$OUT"
          DID=$(echo "$OUT" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
          echo "deployment_id=$DID" >> "$GITHUB_OUTPUT"

      - name: Wait until ready
        run: |
          export PYTHONPATH="${{ github.workspace }}"
          python3 -m cli.cns --json wait --deployment-id "${{ steps.deploy.outputs.deployment_id }}" --timeout 900

      - name: Export runtime (service URL hints)
        run: |
          export PYTHONPATH="${{ github.workspace }}"
          python3 -m cli.cns --json runtime --deployment-id "${{ steps.deploy.outputs.deployment_id }}" | tee runtime.json

      - name: Run tests (example)
        run: |
          test -f runtime.json

  cleanup:
    needs: deploy-and-test
    if: always()
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Destroy deployment
        env:
          CNS_API_BASE_URL: ${{ secrets.CNS_API_BASE_URL }}
          CNS_TOKEN: ${{ secrets.CNS_TOKEN }}
        run: |
          export PYTHONPATH="${{ github.workspace }}"
          DID="${{ needs.deploy-and-test.outputs.deployment_id }}"
          if [ -n "$DID" ]; then
            python3 -m cli.cns --json destroy --deployment-id "$DID" || true
          fi
```

Notes:

- Pass **topology** id to `deploy --topology-id`, or **template** id with `deploy --template-id --project-id <uuid>`.
- `wait` exits **0** only when status is `succeeded` (failed/stopped return non-zero).
- Use `health-check` with a persisted **runtime service resource id** from `runtime` JSON when your image exposes HTTP.
- Tune timeouts for real clusters; Docker on a shared runner may need longer waits.

## REST equivalents

| Step | Method | Path |
|------|--------|------|
| Create token | `POST` | `/api-tokens` |
| List tokens | `GET` | `/api-tokens` |
| Revoke | `DELETE` | `/api-tokens/{id}` |
| Deploy | `POST` | `/topologies/{topology_id}/deploy` |
| Poll | `GET` | `/deployments/{deployment_id}` |
| Runtime | `GET` | `/deployments/{deployment_id}/runtime` |
| Health | `POST` | `/deployments/{deployment_id}/runtime/services/{service_id}/health-check` |
| Destroy | `POST` | `/deployments/{deployment_id}/destroy` |

Authorization header: `Authorization: Bearer <jwt-or-api-token>`.
