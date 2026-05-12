#!/usr/bin/env bash
# Show docker-compose.prod.yml service status, then tail backend + frontend logs.
# Run from repository root (or any directory: script cds to repo root).
# Ctrl+C stops the log follow.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f docker-compose.prod.yml)
LOG_SERVICES=(backend frontend)
if [[ $# -gt 0 ]]; then
  LOG_SERVICES=("$@")
fi

echo "=== compose ps ==="
"${COMPOSE[@]}" ps
echo
echo "=== logs (${LOG_SERVICES[*]}) — Ctrl+C to exit ==="
"${COMPOSE[@]}" logs -f --tail=100 "${LOG_SERVICES[@]}"
