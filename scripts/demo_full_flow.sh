#!/usr/bin/env bash
# Full-stack demo: topology → deploy → traffic → failure injection → reconcile/heal → teardown.
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

require_id() {
  local name="$1"
  local val="$2"
  if [[ -z "${val}" || "${val}" == "null" ]]; then
    echo "error: missing required ${name}" >&2
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
require_id "topology id" "${TOPOLOGY_ID}"
echo "topology_id=${TOPOLOGY_ID}"

section "Create host node (${HOST_IP})"
HOST_JSON=$(curl -sf -X POST "${API_BASE}/topologies/${TOPOLOGY_ID}/nodes" \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc \
    --arg ip "${HOST_IP}" \
    '{name:"demo-host", node_type:"host", image:"alpine:latest", ip_address:$ip, config:null}')")
HOST_ID=$(echo "${HOST_JSON}" | jq -r '.id')
require_id "host node id" "${HOST_ID}"
echo "host_node_id=${HOST_ID}"

section "Create service node (${SERVICE_IP})"
SVC_JSON=$(curl -sf -X POST "${API_BASE}/topologies/${TOPOLOGY_ID}/nodes" \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc \
    --arg ip "${SERVICE_IP}" \
    '{name:"demo-service", node_type:"generic", image:"nginx:alpine", ip_address:$ip, config:null}')")
SERVICE_ID=$(echo "${SVC_JSON}" | jq -r '.id')
require_id "service node id" "${SERVICE_ID}"
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
require_id "deployment id" "${DEPLOYMENT_ID}"
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
echo "Demo finished. topology_id=${TOPOLOGY_ID} (topology row kept in DB; runtime destroyed for this deployment)."
