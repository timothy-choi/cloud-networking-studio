#!/usr/bin/env bash
# Remove Docker workloads labeled as Cloud Networking Studio managed resources.
# Safe when nothing matches (no fatal errors from empty lists).

set -euo pipefail

FILTER='label=app=cloud-networking-studio'

echo "Removing CNS-managed containers (${FILTER})..."
while read -r cid; do
  [[ -z "${cid}" ]] && continue
  docker rm -f "${cid}" || true
done < <(docker ps -aq --filter "${FILTER}" 2>/dev/null || true)

echo "Removing CNS-managed networks (${FILTER})..."
while read -r nid; do
  [[ -z "${nid}" ]] && continue
  docker network rm "${nid}" || true
done < <(docker network ls -q --filter "${FILTER}" 2>/dev/null || true)

echo "Cleanup pass complete."
