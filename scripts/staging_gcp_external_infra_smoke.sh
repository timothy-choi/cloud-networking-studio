#!/usr/bin/env bash
# Staging smoke checklist: GCP external infrastructure deployment (Step 57F).
#
# Validates server prerequisites and prints the full manual/API smoke flow.
#
# Usage:
#   ./scripts/staging_gcp_external_infra_smoke.sh
#   CNS_BASE_URL=https://app-staging.example.com ./scripts/staging_gcp_external_infra_smoke.sh
#
# Optional automation (requires bearer token):
#   CNS_SMOKE_TOKEN=<jwt> CNS_TOPOLOGY_ID=<uuid> ./scripts/staging_gcp_external_infra_smoke.sh --check-api

set -euo pipefail

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: missing command: $1" >&2
    exit 1
  }
}

BASE="${CNS_BASE_URL:-http://127.0.0.1}"
BASE="${BASE%/}"
CHECK_API=0
for arg in "$@"; do
  case "$arg" in
    --check-api) CHECK_API=1 ;;
    -h | --help)
      echo "usage: $0 [--check-api]"
      exit 0
      ;;
  esac
done

pass() { echo "  [ok] $*"; }
fail() { echo "  [FAIL] $*"; FAILURES=$((FAILURES + 1)); }

FAILURES=0

echo "=== GCP External Infrastructure Smoke (57F) ==="
echo "CNS_BASE_URL=${BASE}"
echo

echo "== 1. Server prerequisites =="
for var in GOOGLE_APPLICATION_CREDENTIALS CNS_REMOTE_DOCKER_SSH_KEY_PATH CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH; do
  if [[ -n "${!var:-}" ]]; then
    pass "${var}=${!var}"
    if [[ -r "${!var}" ]]; then
      pass "${var} is readable"
    else
      fail "${var} is not readable"
    fi
  else
    fail "${var} is not set"
  fi
done

if [[ -d /opt/cns/secrets ]]; then
  pass "/opt/cns/secrets mount exists"
else
  echo "  [warn] /opt/cns/secrets not found (may be OK outside Docker host)"
fi

echo
echo "== 2. UI smoke checklist (manual) =="
cat <<'EOF'
  [ ] Create GCP docker-vm infrastructure deployment
  [ ] Validate infra → status validated
  [ ] Plan infra → status awaiting_confirmation; safety checklist passes
  [ ] Confirm apply (type APPLY) → status succeeded OR note partial failure state
  [ ] Verify outputs: public_ip, private_ip, ssh_user, instance_name
  [ ] Verify linked remote_docker runtime target appears
  [ ] Validate generated runtime target (External Deployments)
  [ ] Plan + apply small external topology to generated target
  [ ] Verify remote Docker containers on VM
  [ ] Destroy external workload deployment
  [ ] Destroy infrastructure (type DESTROY)
  [ ] Verify infra status destroyed; target inactive; VM gone in GCP console
  [ ] Repeat destroy → no error (idempotent)
EOF

echo
echo "== 3. Partial failure recovery =="
cat <<'EOF'
  [ ] If configuration_failed: Retry configuration OR Destroy infra
  [ ] If registration_failed: Retry configuration OR Destroy infra
  [ ] Destroy works from configuration_failed / registration_failed
EOF

if [[ "$CHECK_API" == "1" ]]; then
  echo
  echo "== 4. API health =="
  need_cmd curl
  need_cmd jq
  code="$(curl -sS -o /tmp/cns-smoke-health.json -w '%{http_code}' "${BASE}/api/health" || true)"
  if [[ "$code" == "200" ]]; then
    pass "GET /api/health → 200"
  else
    fail "GET /api/health → ${code}"
  fi
  if [[ -n "${CNS_SMOKE_TOKEN:-}" && -n "${CNS_TOPOLOGY_ID:-}" ]]; then
    code="$(curl -sS -o /tmp/cns-smoke-infra.json -w '%{http_code}' \
      -H "Authorization: Bearer ${CNS_SMOKE_TOKEN}" \
      "${BASE}/api/topologies/${CNS_TOPOLOGY_ID}/infrastructure-deployments" || true)"
    if [[ "$code" == "200" ]]; then
      pass "GET infrastructure-deployments → 200"
    else
      fail "GET infrastructure-deployments → ${code}"
    fi
  else
    echo "  [skip] Set CNS_SMOKE_TOKEN + CNS_TOPOLOGY_ID for infra list check"
  fi
fi

echo
if [[ "$FAILURES" -gt 0 ]]; then
  echo "Prerequisite checks failed: ${FAILURES}"
  exit 1
fi
echo "Prerequisite checks passed. Complete the manual checklist above on staging."
