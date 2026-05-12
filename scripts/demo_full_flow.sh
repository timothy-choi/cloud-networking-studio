#!/usr/bin/env bash
# Full-stack demo: (1) flat single-bridge lab → traffic → failures → reconcile/heal → teardown;
# (2) routed two-segment lab (host → router → service) → cross-subnet traffic → router restart → reconcile/heal → teardown.
# Requires: curl, jq; backend at API_BASE; Docker engine for real runtime (optional for API-only smoke).

set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing required command: $1" >&2
    exit 1
  }
}

need_cmd curl
need_cmd jq

section() {
  printf '\n=== %s ===\n' "$1"
}

# Usage: require_id "$id" "$human_name" "$raw_json_body"
require_id() {
  local val="$1"
  local name="$2"
  local raw="${3:-}"
  if [[ -z "${val}" || "${val}" == "null" ]]; then
    echo "" >&2
    echo "error: missing or null id — ${name}" >&2
    if [[ -n "${raw}" ]]; then
      echo "--- raw API response ---" >&2
      echo "${raw}" >&2
    fi
    exit 1
  fi
}

# Unique demo subnet in 10.0.0.0/8 private space (avoid colliding with typical lab ranges).
DEMO_TAG="$(date -u +%Y%m%d-%H%M%S)"
THIRD_OCTET="$(( 80 + (RANDOM % 120) ))"
CIDR="10.${THIRD_OCTET}.0.0/24"
HOST_IP="10.${THIRD_OCTET}.0.10"
SERVICE_IP="10.${THIRD_OCTET}.0.20"
TOPO_NAME="CNS Demo ${DEMO_TAG}"

section "Health check"
curl -sf "${API_BASE}/health" | jq .

section "Create topology"
TOPO_JSON=$(curl -sf -X POST "${API_BASE}/topologies" \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc \
    --arg name "${TOPO_NAME}" \
    --arg desc "automated demo ${DEMO_TAG}" \
    '{name:$name, description:$desc, runtime_target:"docker", networking_mode:"docker_bridge", status:"draft"}')")
TOPOLOGY_ID=$(echo "${TOPO_JSON}" | jq -r '.id')
require_id "${TOPOLOGY_ID}" "flat demo: topology id" "${TOPO_JSON}"
echo "topology_id=${TOPOLOGY_ID}"

section "Create host node (${HOST_IP})"
HOST_JSON=$(curl -sf -X POST "${API_BASE}/topologies/${TOPOLOGY_ID}/nodes" \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc \
    --arg ip "${HOST_IP}" \
    '{name:"demo-host", node_type:"host", image:"alpine:latest", ip_address:$ip, config:null}')")
HOST_ID=$(echo "${HOST_JSON}" | jq -r '.id')
require_id "${HOST_ID}" "flat demo: host node id" "${HOST_JSON}"
echo "host_node_id=${HOST_ID}"

section "Create service node (${SERVICE_IP})"
SVC_JSON=$(curl -sf -X POST "${API_BASE}/topologies/${TOPOLOGY_ID}/nodes" \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc \
    --arg ip "${SERVICE_IP}" \
    '{name:"demo-service", node_type:"generic", image:"nginx:alpine", ip_address:$ip, config:null}')")
SERVICE_ID=$(echo "${SVC_JSON}" | jq -r '.id')
require_id "${SERVICE_ID}" "flat demo: service node id" "${SVC_JSON}"
echo "service_node_id=${SERVICE_ID}"

section "Create link (subnet ${CIDR})"
LINK_JSON=$(curl -sf -X POST "${API_BASE}/topologies/${TOPOLOGY_ID}/links" \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc \
    --arg sid "${HOST_ID}" \
    --arg tid "${SERVICE_ID}" \
    --arg cidr "${CIDR}" \
    '{source_node_id:$sid, target_node_id:$tid, network_name:"demo-net", cidr:$cidr, config:null}')")
echo "${LINK_JSON}" | jq '{id, network_name, cidr}'

section "Deploy topology"
DEP_JSON=$(curl -sf -X POST "${API_BASE}/topologies/${TOPOLOGY_ID}/deploy")
DEPLOYMENT_ID=$(echo "${DEP_JSON}" | jq -r '.id')
require_id "${DEPLOYMENT_ID}" "flat demo: deployment id" "${DEP_JSON}"
echo "deployment_id=${DEPLOYMENT_ID}"
echo "${DEP_JSON}" | jq '{id, status, runtime_target}'

section "Runtime state (topology)"
curl -sf "${API_BASE}/topologies/${TOPOLOGY_ID}/runtime" | jq '{topology_id, runtime_provider, deployment_status, networks: (.networks|length), containers: (.containers|length)}'

section "Traffic: ping (host → service)"
curl -sf -X POST "${API_BASE}/topologies/${TOPOLOGY_ID}/traffic-tests/ping" \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc \
    --arg s "${HOST_ID}" \
    --arg t "${SERVICE_ID}" \
    '{source_node_id:$s, target_node_id:$t, count:3}')" | jq '{id, status, command}'

section "Traffic: HTTP (host → service)"
curl -sf -X POST "${API_BASE}/topologies/${TOPOLOGY_ID}/traffic-tests/http" \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc \
    --arg s "${HOST_ID}" \
    --arg t "${SERVICE_ID}" \
    '{source_node_id:$s, target_node_id:$t, path:"/", port:80}')" | jq '{id, status, command}'

section "Failure injection: stop service node"
curl -sf -X POST "${API_BASE}/topologies/${TOPOLOGY_ID}/failures/stop-node" \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc --arg t "${SERVICE_ID}" '{target_node_id:$t, description:"demo: stop service"}')" | jq '{id, failure_type, status, result_message}'

section "Reconcile deployment"
curl -sf -X POST "${API_BASE}/deployments/${DEPLOYMENT_ID}/reconcile" | jq '{deployment_id, missing_network, missing_node_ids, stopped_containers}'

section "Heal deployment"
curl -sf -X POST "${API_BASE}/deployments/${DEPLOYMENT_ID}/heal" | jq '{deployment_id, restarted_containers, healing_errors, skipped_missing_resources}'

section "Failure injection: restart host node"
curl -sf -X POST "${API_BASE}/topologies/${TOPOLOGY_ID}/failures/restart-node" \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc --arg h "${HOST_ID}" '{target_node_id:$h, description:"demo: restart host"}')" | jq '{id, failure_type, status}'

section "List failure injections"
curl -sf "${API_BASE}/topologies/${TOPOLOGY_ID}/failures" | jq 'length as $n | "count=\($n)", .[0]'

section "Deployment events (sample)"
curl -sf "${API_BASE}/deployments/${DEPLOYMENT_ID}/events" | jq '.[-6:]'

section "Destroy deployment (runtime teardown)"
DESTROY_JSON=$(curl -sf -X POST "${API_BASE}/deployments/${DEPLOYMENT_ID}/destroy")
echo "${DESTROY_JSON}" | jq '{id, status}'

section "Verify API teardown state"
DEP_STATUS=$(curl -sf "${API_BASE}/deployments/${DEPLOYMENT_ID}" | jq -r '.status')
echo "deployment status=${DEP_STATUS}"
if [[ "${DEP_STATUS}" != "stopped" ]]; then
  echo "warning: expected deployment status 'stopped', got '${DEP_STATUS}'" >&2
fi

# --- Routed multi-network lab (fixed 10.72.x / 10.73.x — host → router → service) ---
ROUTED_TMP_RESP="$(mktemp)"
trap 'rm -f "${ROUTED_TMP_RESP}"' EXIT

die_routed() {
  echo "" >&2
  echo "=== DEMO FAILED: routed lab ===" >&2
  echo "Step: $*" >&2
  exit 1
}

# Usage: require_routed_traffic_ok "label" "$json_body"
require_routed_traffic_ok() {
  local label="$1"
  local body="$2"
  local st rc
  st=$(echo "${body}" | jq -r '.status // empty')
  rc=$(echo "${body}" | jq -r '.result.success // empty')
  if [[ "${st}" != "succeeded" || "${rc}" != "true" ]]; then
    echo "" >&2
    echo "=== routed traffic check failed: ${label} ===" >&2
    echo "status=${st} result.success=${rc}" >&2
    echo "${body}" | jq . >&2 || echo "${body}" >&2
    die_routed "${label}: expected succeeded/true"
  fi
}

CIDR_A="10.72.0.0/24"
CIDR_B="10.73.0.0/24"
HOST_IP_A="10.72.0.10"
ROUTER_IP_A="10.72.0.1"
ROUTER_IP_B="10.73.0.1"
SVC_IP_B="10.73.0.20"
ROUTED_TOPO_NAME="CNS Routed ${DEMO_TAG}"

section "Routed demo: create topology (${ROUTED_TOPO_NAME})"
HTTP=$(curl -sS -o "${ROUTED_TMP_RESP}" -w '%{http_code}' \
  -X POST "${API_BASE}/topologies" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n \
    --arg name "${ROUTED_TOPO_NAME}" \
    --arg desc "routed multinet ${DEMO_TAG}" \
    '{name:$name, description:$desc, runtime_target:"docker", networking_mode:"docker_bridge", status:"draft"}')") \
  || die_routed "create topology: curl transport error (exit $?)"
ROUTED_TOPO_JSON="$(cat "${ROUTED_TMP_RESP}")"
printf '\n=== routed raw: create topology (HTTP %s) ===\n' "${HTTP}"
{ echo "${ROUTED_TOPO_JSON}" | jq . 2>/dev/null; } || echo "${ROUTED_TOPO_JSON}"
[[ "${HTTP}" == "201" ]] || die_routed "create topology: expected HTTP 201, got ${HTTP}"
ROUTED_TOPOLOGY_ID="$(echo "${ROUTED_TOPO_JSON}" | jq -r '.id // empty')"
require_id "${ROUTED_TOPOLOGY_ID}" "routed: topology id" "${ROUTED_TOPO_JSON}"
echo "routed_topology_id=${ROUTED_TOPOLOGY_ID}"

section "Routed demo: create node host-a (${HOST_IP_A})"
HTTP=$(curl -sS -o "${ROUTED_TMP_RESP}" -w '%{http_code}' \
  -X POST "${API_BASE}/topologies/${ROUTED_TOPOLOGY_ID}/nodes" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n \
    --arg ip "${HOST_IP_A}" \
    '{name:"host-a", node_type:"host", image:"alpine:latest", ip_address:$ip, config:null}')") \
  || die_routed "create host-a: curl transport error (exit $?)"
RH_JSON="$(cat "${ROUTED_TMP_RESP}")"
printf '\n=== routed raw: create host-a (HTTP %s) ===\n' "${HTTP}"
{ echo "${RH_JSON}" | jq . 2>/dev/null; } || echo "${RH_JSON}"
[[ "${HTTP}" == "201" ]] || die_routed "create host-a: expected HTTP 201, got ${HTTP}"
ROUTED_HOST_ID="$(echo "${RH_JSON}" | jq -r '.id // empty')"
require_id "${ROUTED_HOST_ID}" "routed: host-a node id" "${RH_JSON}"
echo "routed_host_node_id=${ROUTED_HOST_ID}"

section "Routed demo: create node router-1 (net-a ${ROUTER_IP_A}, net-b ${ROUTER_IP_B} via links)"
HTTP=$(curl -sS -o "${ROUTED_TMP_RESP}" -w '%{http_code}' \
  -X POST "${API_BASE}/topologies/${ROUTED_TOPOLOGY_ID}/nodes" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n \
    '{name:"router-1", node_type:"router", image:"alpine:latest", ip_address:null, config:null}')") \
  || die_routed "create router-1: curl transport error (exit $?)"
ROUTER_JSON="$(cat "${ROUTED_TMP_RESP}")"
printf '\n=== routed raw: create router-1 (HTTP %s) ===\n' "${HTTP}"
{ echo "${ROUTER_JSON}" | jq . 2>/dev/null; } || echo "${ROUTER_JSON}"
[[ "${HTTP}" == "201" ]] || die_routed "create router-1: expected HTTP 201, got ${HTTP}"
ROUTED_ROUTER_ID="$(echo "${ROUTER_JSON}" | jq -r '.id // empty')"
require_id "${ROUTED_ROUTER_ID}" "routed: router-1 node id" "${ROUTER_JSON}"
echo "routed_router_node_id=${ROUTED_ROUTER_ID}"

section "Routed demo: create node service-b (${SVC_IP_B})"
HTTP=$(curl -sS -o "${ROUTED_TMP_RESP}" -w '%{http_code}' \
  -X POST "${API_BASE}/topologies/${ROUTED_TOPOLOGY_ID}/nodes" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n \
    --arg ip "${SVC_IP_B}" \
    '{name:"service-b", node_type:"generic", image:"busybox:1.36", ip_address:$ip, config:null}')") \
  || die_routed "create service-b: curl transport error (exit $?)"
RS_JSON="$(cat "${ROUTED_TMP_RESP}")"
printf '\n=== routed raw: create service-b (HTTP %s) ===\n' "${HTTP}"
{ echo "${RS_JSON}" | jq . 2>/dev/null; } || echo "${RS_JSON}"
[[ "${HTTP}" == "201" ]] || die_routed "create service-b: expected HTTP 201, got ${HTTP}"
ROUTED_SERVICE_ID="$(echo "${RS_JSON}" | jq -r '.id // empty')"
require_id "${ROUTED_SERVICE_ID}" "routed: service-b node id" "${RS_JSON}"
echo "routed_service_node_id=${ROUTED_SERVICE_ID}"

section "Routed demo: link host-a → router-1 (net-a ${CIDR_A})"
HTTP=$(curl -sS -o "${ROUTED_TMP_RESP}" -w '%{http_code}' \
  -X POST "${API_BASE}/topologies/${ROUTED_TOPOLOGY_ID}/links" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n \
    --arg sid "${ROUTED_HOST_ID}" \
    --arg tid "${ROUTED_ROUTER_ID}" \
    --arg cidr "${CIDR_A}" \
    --arg gw "${ROUTER_IP_A}" \
    --arg sip "${HOST_IP_A}" \
    --arg tip "${ROUTER_IP_A}" \
    '{source_node_id:$sid, target_node_id:$tid, network_name:"net-a", cidr:$cidr, gateway:$gw, source_endpoint_ip:$sip, target_endpoint_ip:$tip, config:null}')") \
  || die_routed "create link net-a: curl transport error (exit $?)"
ROUTED_LINK_A_JSON="$(cat "${ROUTED_TMP_RESP}")"
printf '\n=== routed raw: link net-a host→router (HTTP %s) ===\n' "${HTTP}"
{ echo "${ROUTED_LINK_A_JSON}" | jq . 2>/dev/null; } || echo "${ROUTED_LINK_A_JSON}"
[[ "${HTTP}" == "201" ]] || die_routed "create link net-a: expected HTTP 201, got ${HTTP}"
ROUTED_LINK_A_ID="$(echo "${ROUTED_LINK_A_JSON}" | jq -r '.id // empty')"
require_id "${ROUTED_LINK_A_ID}" "routed: link net-a id" "${ROUTED_LINK_A_JSON}"
echo "routed_link_net_a_id=${ROUTED_LINK_A_ID}"

section "Routed demo: link router-1 → service-b (net-b ${CIDR_B})"
HTTP=$(curl -sS -o "${ROUTED_TMP_RESP}" -w '%{http_code}' \
  -X POST "${API_BASE}/topologies/${ROUTED_TOPOLOGY_ID}/links" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n \
    --arg sid "${ROUTED_ROUTER_ID}" \
    --arg tid "${ROUTED_SERVICE_ID}" \
    --arg cidr "${CIDR_B}" \
    --arg gw "${ROUTER_IP_B}" \
    --arg sip "${ROUTER_IP_B}" \
    --arg tip "${SVC_IP_B}" \
    '{source_node_id:$sid, target_node_id:$tid, network_name:"net-b", cidr:$cidr, gateway:$gw, source_endpoint_ip:$sip, target_endpoint_ip:$tip, config:null}')") \
  || die_routed "create link net-b: curl transport error (exit $?)"
ROUTED_LINK_B_JSON="$(cat "${ROUTED_TMP_RESP}")"
printf '\n=== routed raw: link net-b router→service (HTTP %s) ===\n' "${HTTP}"
{ echo "${ROUTED_LINK_B_JSON}" | jq . 2>/dev/null; } || echo "${ROUTED_LINK_B_JSON}"
[[ "${HTTP}" == "201" ]] || die_routed "create link net-b: expected HTTP 201, got ${HTTP}"
ROUTED_LINK_B_ID="$(echo "${ROUTED_LINK_B_JSON}" | jq -r '.id // empty')"
require_id "${ROUTED_LINK_B_ID}" "routed: link net-b id" "${ROUTED_LINK_B_JSON}"
echo "routed_link_net_b_id=${ROUTED_LINK_B_ID}"

section "Routed demo: deploy"
HTTP=$(curl -sS -o "${ROUTED_TMP_RESP}" -w '%{http_code}' \
  -X POST "${API_BASE}/topologies/${ROUTED_TOPOLOGY_ID}/deploy") \
  || die_routed "deploy: curl transport error (exit $?)"
ROUTED_DEP_JSON="$(cat "${ROUTED_TMP_RESP}")"
printf '\n=== routed raw: deploy (HTTP %s) ===\n' "${HTTP}"
{ echo "${ROUTED_DEP_JSON}" | jq . 2>/dev/null; } || echo "${ROUTED_DEP_JSON}"
if [[ "${HTTP}" != "201" ]]; then
  echo "" >&2
  echo "=== routed deploy failed: full response (HTTP ${HTTP}) ===" >&2
  echo "${ROUTED_DEP_JSON}" >&2
  ROUTED_ERR_DEP_ID="$(echo "${ROUTED_DEP_JSON}" | jq -r '.id // empty')"
  if [[ -n "${ROUTED_ERR_DEP_ID}" && "${ROUTED_ERR_DEP_ID}" != "null" ]]; then
    echo "" >&2
    echo "=== routed deploy: deployment events for ${ROUTED_ERR_DEP_ID} ===" >&2
    curl -sS "${API_BASE}/deployments/${ROUTED_ERR_DEP_ID}/events" | jq . >&2 || true
  fi
  die_routed "deploy: expected HTTP 201, got ${HTTP} (see full response and events above)"
fi
ROUTED_DEPLOYMENT_ID="$(echo "${ROUTED_DEP_JSON}" | jq -r '.id // empty')"
require_id "${ROUTED_DEPLOYMENT_ID}" "routed: deployment id" "${ROUTED_DEP_JSON}"
echo "routed_deployment_id=${ROUTED_DEPLOYMENT_ID}"
echo "${ROUTED_DEP_JSON}" | jq '{id, status, runtime_target}'

section "Routed verification: runtime + all interface mappings"
curl -sf "${API_BASE}/topologies/${ROUTED_TOPOLOGY_ID}/runtime" | jq '{
  deployment_status,
  latest_deployment_id,
  router: [.containers[] | select(.node_id == $rid) | {
    name, node_id, forwarding_role, ip_forward_enabled,
    routes_lines: (.routes_lines[:8]),
    interface_lines: (.interface_lines[:8]),
    network_interfaces, ipv4_by_network
  }] | .[0]
}' --arg rid "${ROUTED_ROUTER_ID}"
curl -sf "${API_BASE}/topologies/${ROUTED_TOPOLOGY_ID}/runtime" | jq '.containers[] | {name, node_id, running, forwarding_role, ip_forward_enabled, network_interfaces, ipv4_by_network}'

section "Routed verification: ping host-a → router-1"
ROUTED_JSON="$(curl -sf -X POST "${API_BASE}/topologies/${ROUTED_TOPOLOGY_ID}/traffic-tests/ping" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n \
    --arg s "${ROUTED_HOST_ID}" \
    --arg t "${ROUTED_ROUTER_ID}" \
    '{source_node_id:$s, target_node_id:$t, count:3}')")"
echo "${ROUTED_JSON}" | jq '{id, status, command, result}'
require_routed_traffic_ok "ping host-a → router-1" "${ROUTED_JSON}"

section "Routed verification: ping router-1 → host-a"
ROUTED_JSON="$(curl -sf -X POST "${API_BASE}/topologies/${ROUTED_TOPOLOGY_ID}/traffic-tests/ping" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n \
    --arg s "${ROUTED_ROUTER_ID}" \
    --arg t "${ROUTED_HOST_ID}" \
    '{source_node_id:$s, target_node_id:$t, count:3}')")"
echo "${ROUTED_JSON}" | jq '{id, status, command, result}'
require_routed_traffic_ok "ping router-1 → host-a" "${ROUTED_JSON}"

section "Routed verification: ping router-1 → service-b"
ROUTED_JSON="$(curl -sf -X POST "${API_BASE}/topologies/${ROUTED_TOPOLOGY_ID}/traffic-tests/ping" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n \
    --arg s "${ROUTED_ROUTER_ID}" \
    --arg t "${ROUTED_SERVICE_ID}" \
    '{source_node_id:$s, target_node_id:$t, count:3}')")"
echo "${ROUTED_JSON}" | jq '{id, status, command, result}'
require_routed_traffic_ok "ping router-1 → service-b" "${ROUTED_JSON}"

section "Routed verification: ping host-a → service-b (routed path)"
ROUTED_JSON="$(curl -sf -X POST "${API_BASE}/topologies/${ROUTED_TOPOLOGY_ID}/traffic-tests/ping" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n \
    --arg s "${ROUTED_HOST_ID}" \
    --arg t "${ROUTED_SERVICE_ID}" \
    '{source_node_id:$s, target_node_id:$t, count:3}')")"
echo "${ROUTED_JSON}" | jq '{id, status, command, result}'
require_routed_traffic_ok "ping host-a → service-b" "${ROUTED_JSON}"

section "Routed verification: HTTP host-a → service-b"
ROUTED_JSON="$(curl -sf -X POST "${API_BASE}/topologies/${ROUTED_TOPOLOGY_ID}/traffic-tests/http" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n \
    --arg s "${ROUTED_HOST_ID}" \
    --arg t "${ROUTED_SERVICE_ID}" \
    '{source_node_id:$s, target_node_id:$t, path:"/", port:80}')")"
echo "${ROUTED_JSON}" | jq '{id, status, command, result}'
require_routed_traffic_ok "HTTP host-a → service-b" "${ROUTED_JSON}"

section "Routed verification: ping service-b → host-a (return path)"
ROUTED_JSON="$(curl -sf -X POST "${API_BASE}/topologies/${ROUTED_TOPOLOGY_ID}/traffic-tests/ping" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n \
    --arg s "${ROUTED_SERVICE_ID}" \
    --arg t "${ROUTED_HOST_ID}" \
    '{source_node_id:$s, target_node_id:$t, count:3}')")"
echo "${ROUTED_JSON}" | jq '{id, status, command, result}'
require_routed_traffic_ok "ping service-b → host-a" "${ROUTED_JSON}"

section "Routed demo: failure injection — restart router"
curl -sf -X POST "${API_BASE}/topologies/${ROUTED_TOPOLOGY_ID}/failures/restart-node" \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc --arg r "${ROUTED_ROUTER_ID}" '{target_node_id:$r, description:"demo: restart router"}')" | jq '{id, failure_type, status}'

section "Routed demo: reconcile + heal"
curl -sf -X POST "${API_BASE}/deployments/${ROUTED_DEPLOYMENT_ID}/reconcile" | jq '{deployment_id, missing_network, stopped_containers}'
curl -sf -X POST "${API_BASE}/deployments/${ROUTED_DEPLOYMENT_ID}/heal" | jq '{deployment_id, restarted_containers, healing_errors}'

section "Routed demo: traffic ping after heal"
ROUTED_JSON="$(curl -sf -X POST "${API_BASE}/topologies/${ROUTED_TOPOLOGY_ID}/traffic-tests/ping" \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc \
    --arg s "${ROUTED_HOST_ID}" \
    --arg t "${ROUTED_SERVICE_ID}" \
    '{source_node_id:$s, target_node_id:$t, count:2}')")"
echo "${ROUTED_JSON}" | jq '{id, status, command, result}'
require_routed_traffic_ok "ping host-a → service-b after heal" "${ROUTED_JSON}"

section "Routed demo: destroy deployment"
ROUTED_DESTROY_JSON=$(curl -sf -X POST "${API_BASE}/deployments/${ROUTED_DEPLOYMENT_ID}/destroy")
echo "${ROUTED_DESTROY_JSON}" | jq '{id, status}'

section "Verify Docker cleanup (optional)"
if command -v docker >/dev/null 2>&1; then
  CNT=$(docker ps -aq --filter 'label=cns.project=cloud-networking-studio' | wc -l | tr -d ' ')
  NET=$(docker network ls -q --filter 'label=cns.project=cloud-networking-studio' | wc -l | tr -d ' ')
  echo "remaining CNS-labeled containers: ${CNT}"
  echo "remaining CNS-labeled networks: ${NET}"
  if [[ "${CNT}" != "0" || "${NET}" != "0" ]]; then
    echo "hint: run scripts/cleanup_cns_docker.sh if stray resources remain"
  fi
else
  echo "(docker not in PATH — skipping engine-level verification)"
fi

section "Done"
echo "Demo finished. flat_topology_id=${TOPOLOGY_ID} routed_topology_id=${ROUTED_TOPOLOGY_ID} (topology rows kept; runtimes destroyed)."
