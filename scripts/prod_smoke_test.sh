#!/usr/bin/env bash
# Production smoke test: same-origin stack behind Caddy (docker-compose.prod.yml).
# Usage:
#   ./scripts/prod_smoke_test.sh
#   CNS_BASE_URL=http://your-ec2-host ./scripts/prod_smoke_test.sh
#   ./scripts/prod_smoke_test.sh --topology   # optional POST /api/topologies (draft only)
#
# Requires: curl. Optional --topology requires jq.

set -euo pipefail

WITH_TOPOLOGY=0
for arg in "$@"; do
  case "$arg" in
    --topology) WITH_TOPOLOGY=1 ;;
    -h|--help)
      echo "usage: $0 [--topology]"
      echo "  CNS_BASE_URL   default http://127.0.0.1"
      exit 0
      ;;
  esac
done

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: missing required command: $1" >&2
    exit 1
  }
}

need_cmd curl

BASE="${CNS_BASE_URL:-http://127.0.0.1}"
BASE="${BASE%/}"

PASS=0
FAIL=0

ok() {
  echo "PASS  $*"
  PASS=$((PASS + 1))
}

bad() {
  echo "FAIL  $*" >&2
  FAIL=$((FAIL + 1))
}

echo "=== Cloud Networking Studio — production smoke ==="
echo "base_url=${BASE}"
echo

code="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 15 "${BASE}/" || true)"
if [[ "$code" == "200" ]]; then
  ok "GET / (frontend) HTTP ${code}"
else
  bad "GET / (frontend) expected HTTP 200, got ${code}"
fi

health_raw="$(curl -sS --connect-timeout 5 --max-time 15 "${BASE}/api/health" || true)"
if echo "$health_raw" | grep -q '"status"'; then
  ok "GET /api/health returns JSON with status"
  preview="$(printf '%s' "$health_raw" | tr -d '\n' | head -c 120)"
  echo "       ${preview}…"
else
  bad "GET /api/health missing expected JSON (got: ${health_raw:0:200})"
fi

if [[ "$WITH_TOPOLOGY" -eq 1 ]]; then
  need_cmd jq
  tag="$(date -u +%Y%m%d-%H%M%S)"
  body="$(jq -nc \
    --arg name "smoke-${tag}" \
    '{name:$name, description:"prod_smoke_test", runtime_target:"docker", networking_mode:"docker_bridge", status:"draft"}')"
  topo_resp="$(curl -sS --connect-timeout 5 --max-time 30 \
    -X POST "${BASE}/api/topologies" \
    -H 'Content-Type: application/json' \
    -d "$body" || true)"
  tid="$(echo "$topo_resp" | jq -r '.id // empty')"
  if [[ -n "$tid" && "$tid" != "null" ]]; then
    ok "POST /api/topologies (draft) id=${tid}"
  else
    bad "POST /api/topologies failed: ${topo_resp:0:400}"
  fi
fi

echo
if [[ "$FAIL" -eq 0 ]]; then
  echo "RESULT: all checks passed (${PASS} passed)"
  exit 0
fi

echo "RESULT: ${FAIL} check(s) failed, ${PASS} passed" >&2
exit 1
