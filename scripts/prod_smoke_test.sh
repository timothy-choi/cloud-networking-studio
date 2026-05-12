#!/usr/bin/env bash
# Production smoke test: same-origin stack behind Caddy (docker-compose.prod.yml).
# Usage:
#   ./scripts/prod_smoke_test.sh
#   CNS_BASE_URL=http://your-ec2-host ./scripts/prod_smoke_test.sh
#   CNS_HEAVY_SMOKE=1 ./scripts/prod_smoke_test.sh   # also deploy + destroy (needs Docker from backend)
#   ./scripts/prod_smoke_test.sh --heavy            # same as CNS_HEAVY_SMOKE=1
#
# Requires: curl, jq.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$REPO_ROOT/docker-compose.prod.yml}"

HEAVY=0
for arg in "$@"; do
  case "$arg" in
    --heavy) HEAVY=1 ;;
    -h | --help)
      echo "usage: $0 [--heavy]"
      echo "  CNS_BASE_URL       default http://127.0.0.1"
      echo "  CNS_HEAVY_SMOKE=1  optional deploy/destroy against real Docker (CI sets this when enabled)"
      exit 0
      ;;
  esac
done
if [[ "${CNS_HEAVY_SMOKE:-}" == "1" ]]; then
  HEAVY=1
fi

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: missing required command: $1" >&2
    exit 1
  }
}

need_cmd curl
need_cmd jq

BASE="${CNS_BASE_URL:-http://127.0.0.1}"
BASE="${BASE%/}"

BODY="$(mktemp)"
trap 'rm -f "$BODY"' EXIT

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

dump_compose_logs() {
  echo "=== docker compose logs (caddy, frontend, backend) ===" >&2
  if command -v docker >/dev/null 2>&1; then
    docker compose -f "$COMPOSE_FILE" logs --no-color --tail=250 caddy frontend backend 2>&1 || true
  else
    echo "(docker not in PATH — skipping compose logs)" >&2
  fi
}

curl_verbose_edge() {
  echo "=== curl -v GET ${BASE}/ ===" >&2
  curl -v --connect-timeout 5 --max-time 25 "${BASE}/" 2>&1 || true
  echo "=== curl -v GET ${BASE}/api/health ===" >&2
  curl -v --connect-timeout 5 --max-time 25 "${BASE}/api/health" 2>&1 || true
}

echo "=== Cloud Networking Studio — production smoke ==="
echo "base_url=${BASE}  heavy=${HEAVY}"
echo

CADDY_READY=0
if bash "$SCRIPT_DIR/wait_caddy_edge.sh" "$BASE" 30 2 "$BODY"; then
  CADDY_READY=1
  ok "GET / (frontend via Caddy) HTTP 200 after edge wait"
  ok "GET /api/health (API via Caddy) HTTP 200 with JSON status"
  health_raw="$(cat "$BODY")"
  preview="$(printf '%s' "$health_raw" | tr -d '\n' | head -c 120)"
  echo "       ${preview}…"
else
  bad "Caddy edge not ready within 30 attempts × 2s (GET / and GET /api/health)"
fi

if [[ "$CADDY_READY" -ne 1 ]]; then
  curl_verbose_edge
  dump_compose_logs
  echo "RESULT: ${FAIL} check(s) failed, ${PASS} passed" >&2
  exit 1
fi

tag="$(date -u +%Y%m%d-%H%M%S)"
create_body="$(jq -nc \
  --arg name "smoke-${tag}" \
  '{name:$name, description:"prod_smoke_test", runtime_target:"docker", networking_mode:"docker_bridge", status:"draft"}')"
http_topo="$(curl -sS --connect-timeout 5 --max-time 30 \
  -o "$BODY" -w '%{http_code}' \
  -X POST "${BASE}/api/topologies" \
  -H 'Content-Type: application/json' \
  -d "$create_body" || true)"
topo_json="$(cat "$BODY")"
tid="$(echo "$topo_json" | jq -r '.id // empty')"
if [[ "$http_topo" == "201" && -n "$tid" && "$tid" != "null" ]]; then
  ok "POST /api/topologies (blank draft) id=${tid}"
else
  bad "POST /api/topologies expected HTTP 201 with id (http=${http_topo} body=${topo_json:0:400})"
  tid=""
fi

if [[ -n "$tid" ]]; then
  list_raw="$(curl -sS --connect-timeout 5 --max-time 30 "${BASE}/api/topologies" || true)"
  if echo "$list_raw" | jq -e --arg id "$tid" 'map(select(.id == $id)) | length == 1' >/dev/null 2>&1; then
    ok "GET /api/topologies includes new topology ${tid}"
  else
    bad "GET /api/topologies missing id=${tid} (sample: ${list_raw:0:400})"
  fi
else
  bad "skip list check — no topology id"
fi

if [[ "$HEAVY" -eq 1 && -n "$tid" ]]; then
  echo
  echo "--- heavy: deploy + destroy ---"
  htag="$(date -u +%Y%m%d-%H%M%S)"
  # Small lab: service (busybox) + host on one bridge (mirrors backend integration style).
  na="$(curl -sS --connect-timeout 5 --max-time 30 \
    -X POST "${BASE}/api/topologies/${tid}/nodes" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"svc-${htag}\",\"node_type\":\"generic\",\"image\":\"busybox:latest\",\"ip_address\":\"10.0.0.2\",\"config\":null}" \
    | jq -r '.id // empty')"
  nb="$(curl -sS --connect-timeout 5 --max-time 30 \
    -X POST "${BASE}/api/topologies/${tid}/nodes" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"host-${htag}\",\"node_type\":\"host\",\"image\":null,\"ip_address\":\"10.0.0.3\",\"config\":null}" \
    | jq -r '.id // empty')"
  if [[ -z "$na" || "$na" == "null" || -z "$nb" || "$nb" == "null" ]]; then
    bad "heavy: failed to create nodes (na=${na} nb=${nb})"
  else
    ok "heavy: created nodes svc=${na} host=${nb}"
    link_body="$(jq -nc \
      --arg a "$na" \
      --arg b "$nb" \
      '{source_node_id:$a, target_node_id:$b, network_name:"net0", cidr:"10.0.0.0/24", config:null}')"
    lh="$(curl -sS --connect-timeout 5 --max-time 30 \
      -o "$BODY" -w '%{http_code}' \
      -X POST "${BASE}/api/topologies/${tid}/links" \
      -H 'Content-Type: application/json' \
      -d "$link_body" || true)"
    if [[ "$lh" == "201" ]]; then
      ok "heavy: POST link (flat bridge)"
      dh="$(curl -sS --connect-timeout 5 --max-time 600 \
        -o "$BODY" -w '%{http_code}' \
        -X POST "${BASE}/api/topologies/${tid}/deploy" || true)"
      dep_json="$(cat "$BODY")"
      dst="$(echo "$dep_json" | jq -r '.status // empty')"
      did="$(echo "$dep_json" | jq -r '.id // empty')"
      if [[ "$dh" == "201" && "$dst" == "succeeded" && -n "$did" && "$did" != "null" ]]; then
        ok "heavy: deploy succeeded deployment_id=${did}"
        esh="$(curl -sS --connect-timeout 5 --max-time 180 \
          -o "$BODY" -w '%{http_code}' \
          -X POST "${BASE}/api/deployments/${did}/destroy" || true)"
        esj="$(cat "$BODY")"
        es="$(echo "$esj" | jq -r '.status // empty')"
        if [[ "$esh" == "200" && "$es" == "stopped" ]]; then
          ok "heavy: destroy deployment ${did} → stopped"
        else
          bad "heavy: destroy failed http=${esh} status=${es} body=${esj:0:400}"
        fi
      else
        bad "heavy: deploy failed http=${dh} status=${dst} body=${dep_json:0:600}"
      fi
    else
      bad "heavy: POST link failed http=${lh} body=$(head -c 400 "$BODY")"
    fi
  fi
fi

echo
if [[ "$FAIL" -eq 0 ]]; then
  echo "RESULT: all checks passed (${PASS} passed)"
  exit 0
fi

curl_verbose_edge
dump_compose_logs
echo "RESULT: ${FAIL} check(s) failed, ${PASS} passed" >&2
exit 1
