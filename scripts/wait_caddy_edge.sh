#!/usr/bin/env bash
# Wait until Caddy serves both the SPA (/) and the API (/api/health) on the public base URL.
# Usage: wait_caddy_edge.sh <base_url> [attempts=30] [sleep_seconds=2] [api_body_outfile]
#
# Exits 0 when GET / returns 200 and GET /api/health returns 200 with JSON containing .status.
# Exits 1 otherwise. Redirects (3xx) are never accepted — curl is invoked without -L.

set -euo pipefail

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: missing required command: $1" >&2
    exit 1
  }
}

need_cmd curl
need_cmd jq

BASE="${1:?base_url required}"
BASE="${BASE%/}"
ATTEMPTS="${2:-30}"
SLEEP="${3:-2}"
API_OUT="${4:-}"

ROOT_TMP="$(mktemp)"
API_TMP="$(mktemp)"
trap 'rm -f "$ROOT_TMP" "$API_TMP"' EXIT

echo "wait_caddy_edge: ${BASE} (up to ${ATTEMPTS} attempts, ${SLEEP}s apart) …" >&2

REDIR_HINTED=0
for i in $(seq 1 "$ATTEMPTS"); do
  # Do not follow redirects — smoke requires 200 from Caddy, not 308 to HTTPS.
  code_root="$(curl -sS -o "$ROOT_TMP" -w '%{http_code}' --connect-timeout 5 --max-time 20 "${BASE}/" 2>/dev/null || true)"
  code_api="$(curl -sS -o "$API_TMP" -w '%{http_code}' --connect-timeout 5 --max-time 20 "${BASE}/api/health" 2>/dev/null || true)"

  if [[ "$REDIR_HINTED" -eq 0 ]] && [[ "$code_root" =~ ^3[0-9][0-9]$ || "$code_api" =~ ^3[0-9][0-9]$ ]]; then
    REDIR_HINTED=1
    echo "wait_caddy_edge: got HTTP redirect (${code_root} / ${code_api}) — not following (-L off). For sslip without TLS use CADDYFILE_SSLIP=./deploy/Caddyfile.prod and CNS_CADDY_AUTO_HTTPS=off (see docker-compose.sslip.yml)." >&2
  fi

  health_ok=0
  if [[ "$code_api" == "200" ]] && jq -e '.status' "$API_TMP" >/dev/null 2>&1; then
    health_ok=1
  fi

  if [[ "$code_root" == "200" && "$health_ok" == "1" ]]; then
    echo "wait_caddy_edge: ready after ${i}/${ATTEMPTS} (GET / → ${code_root}, GET /api/health → ${code_api})." >&2
    if [[ -n "$API_OUT" ]]; then
      cp "$API_TMP" "$API_OUT"
    fi
    exit 0
  fi

  echo "wait_caddy_edge: attempt ${i}/${ATTEMPTS}: GET / → ${code_root:-000}, GET /api/health → ${code_api:-000} (sleep ${SLEEP}s)" >&2
  sleep "$SLEEP"
done

echo "wait_caddy_edge: timed out after ${ATTEMPTS} attempts." >&2
exit 1
