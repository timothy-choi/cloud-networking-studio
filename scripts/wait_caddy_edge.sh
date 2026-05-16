#!/usr/bin/env bash
# Wait until the public base URL serves the API (/api/health), and optionally the SPA (/) via Caddy.
# Usage: wait_caddy_edge.sh <base_url> [attempts=30] [sleep_seconds=2] [api_body_outfile] [mode]
#
# mode:
#   (empty / full) — require GET / → 200 and GET /api/health → 200 with JSON .status (same-origin / Caddy edge).
#   api-only       — require only GET /api/health → 200 with JSON .status (dedicated API host, no frontend on BASE).
#
# Optional env: CNS_CURL_CONNECT_TIMEOUT, CNS_CURL_MAX_TIME, CNS_CURL_RETRIES (inner GET retries per attempt).
#
# Exits 0 when conditions met. Redirects (3xx) are never accepted — curl is invoked without -L.

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
MODE="${5:-full}"

# Longer defaults help sslip.io / slow DNS; override with CNS_CURL_CONNECT_TIMEOUT / CNS_CURL_MAX_TIME.
CURL_CT="${CNS_CURL_CONNECT_TIMEOUT:-25}"
CURL_MT="${CNS_CURL_MAX_TIME:-60}"
GET_RETRIES="${CNS_CURL_RETRIES:-4}"

ROOT_TMP="$(mktemp)"
API_TMP="$(mktemp)"
trap 'rm -f "$ROOT_TMP" "$API_TMP"' EXIT

if [[ "$MODE" == "api-only" ]]; then
  echo "wait_caddy_edge: ${BASE} API-only (GET /api/health only), up to ${ATTEMPTS} attempts, ${SLEEP}s apart …" >&2
else
  echo "wait_caddy_edge: ${BASE} (up to ${ATTEMPTS} attempts, ${SLEEP}s apart) …" >&2
fi

REDIR_HINTED=0
for i in $(seq 1 "$ATTEMPTS"); do
  code_root="200"
  if [[ "$MODE" != "api-only" ]]; then
    code_root="000"
    for _r in $(seq 1 "$GET_RETRIES"); do
      code_root="$(curl -sS -o "$ROOT_TMP" -w '%{http_code}' --connect-timeout "$CURL_CT" --max-time "$CURL_MT" "${BASE}/" 2>/dev/null || true)"
      [[ "$code_root" == "200" ]] && break
      sleep 2
    done
  fi

  code_api="000"
  for _r in $(seq 1 "$GET_RETRIES"); do
    code_api="$(curl -sS -o "$API_TMP" -w '%{http_code}' --connect-timeout "$CURL_CT" --max-time "$CURL_MT" "${BASE}/api/health" 2>/dev/null || true)"
    if [[ "$code_api" == "200" ]] && jq -e '.status' "$API_TMP" >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done

  if [[ "$REDIR_HINTED" -eq 0 ]]; then
    if [[ "$MODE" != "api-only" ]] && [[ "$code_root" =~ ^3[0-9][0-9]$ ]]; then
      REDIR_HINTED=1
      echo "wait_caddy_edge: got HTTP redirect on GET / (${code_root}) — not following (-L off). If you need plain HTTP on sslip (no redirect), use CADDYFILE_SSLIP=./deploy/Caddyfile.prod and CNS_CADDY_AUTO_HTTPS=off (see docker-compose.sslip.yml)." >&2
    elif [[ "$code_api" =~ ^3[0-9][0-9]$ ]]; then
      REDIR_HINTED=1
      echo "wait_caddy_edge: got HTTP redirect on GET /api/health (${code_api}) — not following (-L off)." >&2
    fi
  fi

  health_ok=0
  if [[ "$code_api" == "200" ]] && jq -e '.status' "$API_TMP" >/dev/null 2>&1; then
    health_ok=1
  fi

  if [[ "$MODE" == "api-only" ]]; then
    if [[ "$health_ok" == "1" ]]; then
      echo "wait_caddy_edge: API ready after ${i}/${ATTEMPTS} (GET /api/health → ${code_api})." >&2
      if [[ -n "$API_OUT" ]]; then
        cp "$API_TMP" "$API_OUT"
      fi
      exit 0
    fi
    echo "wait_caddy_edge: attempt ${i}/${ATTEMPTS}: GET /api/health → ${code_api:-000} (sleep ${SLEEP}s)" >&2
  else
    if [[ "$code_root" == "200" && "$health_ok" == "1" ]]; then
      echo "wait_caddy_edge: ready after ${i}/${ATTEMPTS} (GET / → ${code_root}, GET /api/health → ${code_api})." >&2
      if [[ -n "$API_OUT" ]]; then
        cp "$API_TMP" "$API_OUT"
      fi
      exit 0
    fi
    echo "wait_caddy_edge: attempt ${i}/${ATTEMPTS}: GET / → ${code_root:-000}, GET /api/health → ${code_api:-000} (sleep ${SLEEP}s)" >&2
  fi
  sleep "$SLEEP"
done

echo "wait_caddy_edge: timed out after ${ATTEMPTS} attempts." >&2
exit 1
