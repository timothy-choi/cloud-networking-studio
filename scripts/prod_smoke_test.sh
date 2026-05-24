#!/usr/bin/env bash
# Production smoke test: same-origin stack behind Caddy (docker-compose.prod.yml).
#
# Step 34+: authenticated topology flow (register/login → project → topology).
# Health-only mode: AUTH_SMOKE=0 skips API checks after edge wait.
#
# Usage:
#   ./scripts/prod_smoke_test.sh
#   CNS_BASE_URL=http://your-ec2-host ./scripts/prod_smoke_test.sh
#   AUTH_SMOKE=0 ./scripts/prod_smoke_test.sh          # health + edge wait only
#   CNS_HEAVY_SMOKE=1 ./scripts/prod_smoke_test.sh   # also deploy + destroy (needs Docker from backend)
#   ./scripts/prod_smoke_test.sh --heavy             # same as CNS_HEAVY_SMOKE=1
#   CNS_SMOKE_API_ONLY=1 …                          # dedicated API host (e.g. https://api.example.com): wait /api/health only; skip GET /
#
# Env (optional):
#   CNS_BASE_URL               full-stack: http://… for sslip EC2 (no curl -L). API-only: https://api… is OK.
#   CNS_SMOKE_API_ONLY         set 1 when BASE is API-only (no SPA on same host); edge wait skips GET /
#   CNS_CURL_CONNECT_TIMEOUT       default 25 (DNS/TCP; sslip.io can be slow)
#   CNS_CURL_MAX_TIME              default 120
#   CNS_CURL_RETRIES               default 4 — inner GET retries (wait_caddy_edge.sh)
#   CNS_API_CURL_RETRIES           default 6 — retries for API JSON calls (DNS/connect flakes)
#   CNS_WAIT_ATTEMPTS              passed to wait_caddy_edge (default 30)
#   AUTH_SMOKE                     default 1; set 0 for health-only
#   CNS_SMOKE_UNAUTH_TOPOLOGY_CHECK  default 1; set 0 to skip POST /api/topologies without Bearer
#                                      (e.g. backend AUTH_REQUIRE_LOGIN=false — legacy dev mode)
#   CNS_EXPECT_ENVIRONMENT       if set, require GET /api/health JSON .environment to match (e.g. staging)
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
      echo "  CNS_BASE_URL                    default http://127.0.0.1 — sslip: use http://<EIP>.sslip.io (no -L; avoid 308→HTTPS)"
      echo "  CNS_SMOKE_API_ONLY=1            wait GET /api/health only (custom domain: app on Vercel, API on BASE)"
      echo "  AUTH_SMOKE=0                    health + edge wait only (no JWT / topology checks)"
      echo "  CNS_HEAVY_SMOKE=1               optional deploy/destroy against real Docker (CI sets this when enabled)"
      echo "  CNS_WAIT_ATTEMPTS               passed to wait_caddy_edge (default 30)"
      echo "  CNS_CURL_CONNECT_TIMEOUT        default 25"
      echo "  CNS_CURL_MAX_TIME               default 120"
      echo "  CNS_CURL_RETRIES                default 4 (wait_caddy_edge inner GET retries)"
      echo "  CNS_API_CURL_RETRIES            default 6 (API calls: register, projects, topology POST, …)"
      echo "  CNS_SMOKE_UNAUTH_TOPOLOGY_CHECK  default 1; set 0 if AUTH_REQUIRE_LOGIN=false (no 401 expectation)"
      echo "  CNS_SMOKE_DEBUG                 set 1 for verbose JWT/project logging"
      echo "  Edge checks use curl without -L: only HTTP 200 counts (3xx redirects fail the wait)."
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

API_ONLY=0
if [[ "${CNS_SMOKE_API_ONLY:-0}" == "1" || "${CNS_SMOKE_API_ONLY:-}" == "true" ]]; then
  API_ONLY=1
fi

echo "FINAL_CNS_BASE_URL=${BASE}"
echo "FINAL_CNS_SMOKE_API_ONLY=${CNS_SMOKE_API_ONLY:-}"

# Smoke does not use curl -L: 3xx to HTTPS would fail the edge wait. Full-stack sslip should use http://…
# API-only mode (CNS_SMOKE_API_ONLY=1) targets a dedicated HTTPS API host — HTTPS without warning is expected.
if [[ "$API_ONLY" -ne 1 ]] && [[ "$BASE" == https://* ]]; then
  echo "WARNING: CNS_BASE_URL is HTTPS — full-stack prod smoke expects HTTP on sslip (no -L). Prefer Terraform stack_base_url_sslip_http or set CNS_BASE_URL=http://… (or set CNS_SMOKE_API_ONLY=1 for API-only hosts)." >&2
fi

CURL_CT="${CNS_CURL_CONNECT_TIMEOUT:-25}"
CURL_MT="${CNS_CURL_MAX_TIME:-120}"
API_RETRIES="${CNS_API_CURL_RETRIES:-6}"

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
  if [[ "$API_ONLY" -eq 1 ]]; then
    echo "=== curl -v GET ${BASE}/api/health (API-only smoke) ===" >&2
    curl -v --connect-timeout "$CURL_CT" --max-time "$CURL_MT" "${BASE}/api/health" 2>&1 || true
  else
    echo "=== curl -v GET ${BASE}/ ===" >&2
    curl -v --connect-timeout "$CURL_CT" --max-time "$CURL_MT" "${BASE}/" 2>&1 || true
    echo "=== curl -v GET ${BASE}/api/health ===" >&2
    curl -v --connect-timeout "$CURL_CT" --max-time "$CURL_MT" "${BASE}/api/health" 2>&1 || true
  fi
}

# Retry on empty HTTP code (000), curl failure, or transient 502/503/504 from edge.
smoke_curl_http() {
  local attempt=0
  local http="000"
  local curl_ok=0
  while [[ "$attempt" -lt "$API_RETRIES" ]]; do
    attempt=$((attempt + 1))
    curl_ok=0
    http="$(curl -sS --connect-timeout "$CURL_CT" --max-time "$CURL_MT" \
      -o "$BODY" -w '%{http_code}' "$@" 2>/dev/null)" && curl_ok=1 || true
    if [[ "$curl_ok" -eq 1 ]] && [[ -n "$http" ]] && [[ "$http" != "000" ]]; then
      if [[ "$http" == "502" || "$http" == "503" || "$http" == "504" ]]; then
        echo "smoke_curl_http: HTTP ${http} (attempt ${attempt}/${API_RETRIES}), retrying…" >&2
        sleep 2
        continue
      fi
      printf '%s' "$http"
      return 0
    fi
    echo "smoke_curl_http: attempt ${attempt}/${API_RETRIES} failed or http=${http:-000} (curl_ok=${curl_ok}); retry in 2s…" >&2
    sleep 2
  done
  printf '%s' "${http:-000}"
  return 1
}

print_response_body() {
  local label="$1"
  echo "--- ${label} (response body) ---" >&2
  if [[ ! -s "$BODY" ]]; then
    echo "(empty)" >&2
    return 0
  fi
  if jq -e . "$BODY" >/dev/null 2>&1; then
    jq . "$BODY" >&2 || cat "$BODY" >&2
  else
    cat "$BODY" >&2
  fi
}

# Print full diagnostics when topology POST fails or returns 401/403/422.
debug_topology_post() {
  local http="$1"
  local url="$2"
  local req_json="$3"
  local token="$4"
  echo "=== DEBUG: POST /api/topologies (smoke failure or error status) ===" >&2
  echo "HTTP status: ${http}" >&2
  echo "Request URL: ${url}" >&2
  echo "Request headers:" >&2
  echo "  Content-Type: application/json" >&2
  if [[ -n "${token}" ]]; then
    echo "  Authorization: Bearer <len=${#token} chars>" >&2
  else
    echo "  Authorization: (missing — token empty)" >&2
  fi
  echo "Request body (exact JSON):" >&2
  echo "${req_json}" | jq . >&2 2>/dev/null || echo "${req_json}" >&2
  print_response_body "POST /api/topologies response"
  echo "=== END DEBUG ===" >&2
}

echo "=== Cloud Networking Studio — production smoke ==="
echo "base_url=${BASE}  api_only=${API_ONLY}  heavy=${HEAVY}  AUTH_SMOKE=${AUTH_SMOKE:-1}  curl_ct=${CURL_CT} curl_mt=${CURL_MT} api_retries=${API_RETRIES}"
echo

CADDY_READY=0
WAIT_ATTEMPTS="${CNS_WAIT_ATTEMPTS:-30}"

export CNS_CURL_CONNECT_TIMEOUT="${CNS_CURL_CONNECT_TIMEOUT:-$CURL_CT}"
export CNS_CURL_MAX_TIME="${CNS_CURL_MAX_TIME:-$CURL_MT}"
export CNS_CURL_RETRIES="${CNS_CURL_RETRIES:-4}"

WAIT_EDGE_ARGS=( "$BASE" "$WAIT_ATTEMPTS" 2 "$BODY" )
if [[ "$API_ONLY" -eq 1 ]]; then
  WAIT_EDGE_ARGS+=( api-only )
fi

if bash "$SCRIPT_DIR/wait_caddy_edge.sh" "${WAIT_EDGE_ARGS[@]}"; then
  CADDY_READY=1
  if [[ "$API_ONLY" -eq 1 ]]; then
    ok "GET /api/health (API) HTTP 200 with JSON status"
  else
    ok "GET / (frontend via Caddy) HTTP 200 after edge wait"
    ok "GET /api/health (API via Caddy) HTTP 200 with JSON status"
  fi
  health_raw="$(cat "$BODY")"
  preview="$(printf '%s' "$health_raw" | tr -d '\n' | head -c 120)"
  echo "       ${preview}…"
  if [[ -n "${CNS_EXPECT_ENVIRONMENT:-}" ]]; then
    actual_env="$(printf '%s' "$health_raw" | jq -r '.environment // empty')"
    if [[ "$actual_env" != "$CNS_EXPECT_ENVIRONMENT" ]]; then
      bad "GET /api/health environment expected '${CNS_EXPECT_ENVIRONMENT}', got '${actual_env:-<empty>}'"
    else
      ok "GET /api/health environment=${actual_env}"
    fi
  fi
  http_rs="$(smoke_curl_http "${BASE}/api/runtime/status")"
  if [[ "$http_rs" == "200" ]] && jq -e '.status and .runtime_provider' "$BODY" >/dev/null 2>&1; then
    if [[ "$API_ONLY" -eq 1 ]]; then
      ok "GET /api/runtime/status (API) HTTP 200 with JSON status/runtime_provider"
    else
      ok "GET /api/runtime/status (API via Caddy) HTTP 200 with JSON status/runtime_provider"
    fi
  else
    bad "GET /api/runtime/status expected HTTP 200 with JSON .status and .runtime_provider (got http=${http_rs})"
    print_response_body "GET /api/runtime/status"
  fi
else
  if [[ "$API_ONLY" -eq 1 ]]; then
    bad "API not ready within ${WAIT_ATTEMPTS} attempts × 2s (GET /api/health)"
  else
    bad "Caddy edge not ready within ${WAIT_ATTEMPTS} attempts × 2s (GET / and GET /api/health)"
  fi
fi

if [[ "$CADDY_READY" -ne 1 ]]; then
  curl_verbose_edge
  dump_compose_logs
  echo "RESULT: ${FAIL} check(s) failed, ${PASS} passed" >&2
  exit 1
fi

AUTH_SMOKE="${AUTH_SMOKE:-1}"
if [[ "$AUTH_SMOKE" == "0" || "$AUTH_SMOKE" == "false" ]]; then
  echo
  echo "AUTH_SMOKE=0 — health-only smoke (skipping JWT / project / topology checks)."
  echo "RESULT: all health checks passed (${PASS} passed)"
  exit 0
fi

# --- Optional: unauthenticated topology POST must NOT succeed after Step 34 (legacy 201 smoke disabled).
UNAUTH_CHECK="${CNS_SMOKE_UNAUTH_TOPOLOGY_CHECK:-1}"
if [[ "$UNAUTH_CHECK" == "1" || "$UNAUTH_CHECK" == "true" ]]; then
  tag0="$(date -u +%Y%m%d-%H%M%S)"
  unauth_body="$(jq -nc \
    --arg name "smoke-unauth-${tag0}" \
    '{name:$name, description:"prod_smoke_unauth", runtime_target:"docker", networking_mode:"docker_bridge", status:"draft"}')"
  http_unauth="$(smoke_curl_http \
    -X POST "${BASE}/api/topologies" \
    -H 'Content-Type: application/json' \
    -d "$unauth_body")"
  if [[ "$http_unauth" == "401" ]]; then
    ok "POST /api/topologies without Authorization → 401 (expected after Step 34)"
  else
    bad "POST /api/topologies without Authorization expected HTTP 401, got ${http_unauth}. If AUTH_REQUIRE_LOGIN=false you get 201 from implicit dev user — set AUTH_REQUIRE_LOGIN=true or CNS_SMOKE_UNAUTH_TOPOLOGY_CHECK=0."
    print_response_body "unauthenticated POST /api/topologies"
  fi
else
  echo "CNS_SMOKE_UNAUTH_TOPOLOGY_CHECK=0 — skipping unauthenticated topology POST check."
fi

# --- Register or login smoke user
tag="$(date -u +%Y%m%d-%H%M%S)-$$"
SMOKE_EMAIL="smoke+${tag}@example.com"
SMOKE_PASS="SmokePass-987654"
reg_body="$(jq -nc \
  --arg email "$SMOKE_EMAIL" \
  --arg pass "$SMOKE_PASS" \
  '{email:$email,password:$pass,display_name:"prod-smoke"}')"

http_reg="$(smoke_curl_http \
  -X POST "${BASE}/api/auth/register" \
  -H 'Content-Type: application/json' \
  -d "$reg_body")"
TOKEN=""
http_log=""
if [[ "$http_reg" == "201" ]]; then
  TOKEN="$(jq -r '.access_token // empty' "$BODY")"
elif [[ "$http_reg" == "409" ]]; then
  log_body="$(jq -nc --arg email "$SMOKE_EMAIL" --arg pass "$SMOKE_PASS" '{email:$email,password:$pass}')"
  http_log="$(smoke_curl_http \
    -X POST "${BASE}/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d "$log_body")"
  if [[ "$http_log" == "200" ]]; then
    TOKEN="$(jq -r '.access_token // empty' "$BODY")"
  fi
fi

if [[ -z "$TOKEN" || "$TOKEN" == "null" ]]; then
  echo "=== DEBUG: register/login failed ===" >&2
  echo "POST ${BASE}/api/auth/register → HTTP ${http_reg}" >&2
  echo "Request body:" >&2
  echo "${reg_body}" | jq . >&2 2>/dev/null || echo "$reg_body" >&2
  print_response_body "last auth response"
  bad "auth smoke: register/login failed (register_http=${http_reg} login_http=${http_log:-n/a})"
else
  echo "auth smoke passed (email=${SMOKE_EMAIL}, jwt_len=${#TOKEN})"
  ok "auth smoke: obtained Bearer token from /api/auth/register or /api/auth/login"
fi

if [[ "${CNS_SMOKE_DEBUG:-0}" == "1" ]]; then
  echo "DEBUG: JWT prefix: ${TOKEN:0:24}…" >&2
fi

AUTH_HDR=(-H "Authorization: Bearer ${TOKEN}")

project_id=""
if [[ -n "$TOKEN" && "$TOKEN" != "null" ]]; then
  http_pl="$(smoke_curl_http \
    "${AUTH_HDR[@]}" \
    "${BASE}/api/projects")"
  if [[ "$http_pl" != "200" ]]; then
    echo "=== DEBUG: GET /api/projects failed ===" >&2
    echo "HTTP ${http_pl}" >&2
    print_response_body "GET /api/projects"
    bad "GET /api/projects expected 200, got ${http_pl}"
  else
    project_id="$(jq -r 'if type == "array" then (.[0].id // empty) else (.id // empty) end' "$BODY")"
    if [[ -z "$project_id" || "$project_id" == "null" ]]; then
      proj_body="$(jq -nc --arg n "smoke-proj-${tag}" '{name:$n, description:"prod_smoke_test project"}')"
      http_pc="$(smoke_curl_http \
        -X POST "${BASE}/api/projects" \
        -H 'Content-Type: application/json' \
        "${AUTH_HDR[@]}" \
        -d "$proj_body")"
      if [[ "$http_pc" == "201" ]]; then
        project_id="$(jq -r '.id // empty' "$BODY")"
      else
        echo "=== DEBUG: POST /api/projects failed ===" >&2
        echo "HTTP ${http_pc}" >&2
        print_response_body "POST /api/projects"
      fi
    fi
    if [[ -n "$project_id" && "$project_id" != "null" ]]; then
      echo "project smoke passed (project_id=${project_id})"
      ok "project smoke: have project context for topology"
    else
      bad "project smoke: no project id (register should create default workspace)"
    fi
  fi
fi

if [[ "${CNS_SMOKE_DEBUG:-0}" == "1" ]]; then
  echo "DEBUG: project_id=${project_id}" >&2
fi

tid=""
topo_url="${BASE}/api/topologies"
if [[ -n "$TOKEN" && -n "$project_id" && "$project_id" != "null" ]]; then
  create_body="$(jq -nc \
    --arg name "smoke-${tag}" \
    --arg pid "$project_id" \
    '{name:$name, description:"prod_smoke_test", runtime_target:"docker", networking_mode:"docker_bridge", status:"draft", project_id:$pid}')"
  # Contract: Bearer + JSON body with project_id (matches TopologyCreate).
  http_topo="$(smoke_curl_http \
    -X POST "$topo_url" \
    -H 'Content-Type: application/json' \
    "${AUTH_HDR[@]}" \
    --data-binary "$create_body")"
  topo_json="$(cat "$BODY")"
  tid="$(echo "$topo_json" | jq -r '.id // empty')"
  if [[ "$http_topo" == "201" && -n "$tid" && "$tid" != "null" ]]; then
    echo "topology smoke passed (topology_id=${tid})"
    ok "POST /api/topologies (draft in project) id=${tid}"
  else
    bad "POST /api/topologies expected HTTP 201 with id (http=${http_topo})"
    debug_topology_post "$http_topo" "$topo_url" "$create_body" "$TOKEN"
    if [[ "$http_topo" == "401" || "$http_topo" == "403" || "$http_topo" == "422" ]]; then
      echo "--- (status ${http_topo} — response printed above) ---" >&2
    fi
    tid=""
  fi
fi

if [[ -n "$tid" ]]; then
  list_http="$(smoke_curl_http \
    "${AUTH_HDR[@]}" \
    "${BASE}/api/topologies?project_id=${project_id}" || true)"
  list_json=""
  if [[ "$list_http" == "200" ]]; then
    list_json="$(cat "$BODY")"
  fi
  if [[ "$list_http" == "200" ]] && echo "$list_json" | jq -e --arg id "$tid" 'if type == "array" then (map(select(.id == $id)) | length == 1) else false end' >/dev/null 2>&1; then
    ok "GET /api/topologies?project_id=… includes new topology ${tid}"
  else
    echo "=== DEBUG: GET /api/topologies?project_id=${project_id} → HTTP ${list_http:-?} ===" >&2
    if [[ -n "$list_json" ]]; then
      echo "$list_json" | jq . >&2 2>/dev/null || echo "$list_json" >&2
    else
      print_response_body "GET /api/topologies"
    fi
    bad "GET /api/topologies missing id=${tid} or non-200 (http=${list_http})"
  fi
else
  bad "skip list check — no topology id"
fi

if [[ "$HEAVY" -eq 1 && -n "$tid" && -n "$TOKEN" ]]; then
  echo
  echo "--- heavy: deploy + destroy ---"
  htag="$(date -u +%Y%m%d-%H%M%S)"
  http_na="$(smoke_curl_http \
    "${AUTH_HDR[@]}" \
    -X POST "${BASE}/api/topologies/${tid}/nodes" \
    -H 'Content-Type: application/json' \
    --data-binary "{\"name\":\"svc-${htag}\",\"node_type\":\"generic\",\"image\":\"nginx:alpine\",\"ip_address\":\"10.0.0.2\",\"config\":null}")"
  na=""
  if [[ "$http_na" == "201" ]]; then
    na="$(jq -r '.id // empty' "$BODY")"
  else
    echo "=== DEBUG: POST node (service) http=${http_na} ===" >&2
    print_response_body "POST .../nodes (svc)"
  fi
  http_nb="$(smoke_curl_http \
    "${AUTH_HDR[@]}" \
    -X POST "${BASE}/api/topologies/${tid}/nodes" \
    -H 'Content-Type: application/json' \
    --data-binary "$(jq -nc --arg name "host-${htag}" '{name:$name, node_type:"host", image:"alpine:latest", ip_address:"10.0.0.3", config:{command:["sleep","infinity"]}}')")"
  nb=""
  if [[ "$http_nb" == "201" ]]; then
    nb="$(jq -r '.id // empty' "$BODY")"
  else
    echo "=== DEBUG: POST node (host) http=${http_nb} ===" >&2
    print_response_body "POST .../nodes (host)"
  fi
  if [[ -z "$na" || "$na" == "null" || -z "$nb" || "$nb" == "null" ]]; then
    bad "heavy: failed to create nodes (http_svc=${http_na} http_host=${http_nb} na=${na} nb=${nb})"
  else
    ok "heavy: created nodes svc=${na} host=${nb}"
    link_body="$(jq -nc \
      --arg a "$na" \
      --arg b "$nb" \
      '{source_node_id:$a, target_node_id:$b, network_name:"net0", cidr:"10.0.0.0/24", config:null}')"
    lh="$(smoke_curl_http \
      "${AUTH_HDR[@]}" \
      -X POST "${BASE}/api/topologies/${tid}/links" \
      -H 'Content-Type: application/json' \
      --data-binary "$link_body")"
    if [[ "$lh" == "201" ]]; then
      ok "heavy: POST link (flat bridge)"
      dh="$(smoke_curl_http \
        "${AUTH_HDR[@]}" \
        -X POST "${BASE}/api/topologies/${tid}/deploy")"
      dep_json="$(cat "$BODY")"
      dst="$(echo "$dep_json" | jq -r '.status // empty')"
      did="$(echo "$dep_json" | jq -r '.id // empty')"
      if [[ "$dh" == "201" && "$dst" == "succeeded" && -n "$did" && "$did" != "null" ]]; then
        ok "heavy: deploy succeeded deployment_id=${did}"
        esh="$(smoke_curl_http \
          "${AUTH_HDR[@]}" \
          -X POST "${BASE}/api/deployments/${did}/destroy")"
        esj="$(cat "$BODY")"
        es="$(echo "$esj" | jq -r '.status // empty')"
        if [[ "$esh" == "200" && "$es" == "stopped" ]]; then
          ok "heavy: destroy deployment ${did} → stopped"
        else
          echo "=== DEBUG: destroy deployment http=${esh} ===" >&2
          print_response_body "POST .../destroy"
          bad "heavy: destroy failed http=${esh} status=${es} body=${esj:0:400}"
        fi
      else
        echo "=== DEBUG: deploy http=${dh} status=${dst} ===" >&2
        print_response_body "POST .../deploy"
        bad "heavy: deploy failed http=${dh} status=${dst} body=${dep_json:0:600}"
      fi
    else
      echo "=== DEBUG: POST link http=${lh} ===" >&2
      print_response_body "POST .../links"
      bad "heavy: POST link failed http=${lh}"
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
