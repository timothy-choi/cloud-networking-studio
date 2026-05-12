#!/usr/bin/env bash
# Wait until the production stack (via Caddy) responds — used by GitHub Actions.
# Usage: ./scripts/ci_wait_for_stack.sh [base_url] [timeout_seconds]
# Defaults: base_url=http://127.0.0.1  timeout=90
#
# Delegates to wait_caddy_edge.sh: ~2s between attempts, attempts = ceil(timeout/2) (min 15).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

BASE="${1:-http://127.0.0.1}"
BASE="${BASE%/}"
TIMEOUT="${2:-90}"
SLEEP=2
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$REPO_ROOT/docker-compose.prod.yml}"
ATTEMPTS=$(( (TIMEOUT + SLEEP - 1) / SLEEP ))
if [[ "$ATTEMPTS" -lt 15 ]]; then
  ATTEMPTS=15
fi

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: missing required command: $1" >&2
    exit 1
  }
}

need_cmd bash
need_cmd jq
need_cmd curl

echo "ci_wait_for_stack: ${BASE} — up to ${ATTEMPTS} attempts × ${SLEEP}s (wall ~$((ATTEMPTS * SLEEP))s) …"

if bash "$SCRIPT_DIR/wait_caddy_edge.sh" "$BASE" "$ATTEMPTS" "$SLEEP"; then
  echo "ci_wait_for_stack: stack is up."
  exit 0
fi

echo "error: stack did not become ready within the allotted time" >&2
docker compose -f "$COMPOSE_FILE" ps -a 2>/dev/null || true
docker compose -f "$COMPOSE_FILE" logs --no-color --tail=200 caddy frontend backend 2>/dev/null || true
exit 1
