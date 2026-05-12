#!/usr/bin/env bash
# Restart the production compose stack (docker-compose.prod.yml) without removing volumes.
# Run from anywhere; changes directory to the repository root.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f docker-compose.prod.yml)

echo "=== restarting cns-prod services ==="
"${COMPOSE[@]}" restart
echo "=== compose ps ==="
"${COMPOSE[@]}" ps
