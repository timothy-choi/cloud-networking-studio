#!/usr/bin/env bash
# EC2 host bootstrap: cloud-init diagnostics + robust Docker install/wait.
#
# Usage:
#   bash scripts/ec2_bootstrap_docker.sh
#   source scripts/ec2_bootstrap_docker.sh && ec2_bootstrap_host
#
# Exits non-zero if Docker is unavailable after CNS_DOCKER_WAIT_SECONDS (default 300).

set -euo pipefail

CNS_DOCKER_WAIT_SECONDS="${CNS_DOCKER_WAIT_SECONDS:-300}"

_cns_log() {
  echo "[cns-bootstrap] $*"
}

_cns_die() {
  _cns_log "FATAL: $*"
  exit 1
}

_cns_retry() {
  local attempts="$1"
  local delay="$2"
  shift 2
  local n=1
  while (( n <= attempts )); do
    if "$@"; then
      return 0
    fi
    if (( n == attempts )); then
      return 1
    fi
    _cns_log "Attempt ${n}/${attempts} failed; retrying in ${delay}s: $*"
    sleep "$delay"
    n=$((n + 1))
  done
}

_cns_cloud_init_report() {
  local status=""
  status="$(sudo cloud-init status 2>/dev/null || true)"
  echo "=== cloud-init status ==="
  echo "${status}"
  if [[ "${status}" == *"error"* ]]; then
    echo "=== cloud-init status --long ==="
    sudo cloud-init status --long || true
    echo "=== tail /var/log/cloud-init-output.log ==="
    sudo tail -n 200 /var/log/cloud-init-output.log || true
  fi
}

_cns_wait_for_cloud_init() {
  _cns_log "Waiting for cloud-init..."
  if ! sudo cloud-init status --wait; then
    _cns_cloud_init_report
    _cns_die "cloud-init did not complete successfully"
  fi
  _cns_cloud_init_report
}

_cns_apt_get_update() {
  export DEBIAN_FRONTEND=noninteractive
  _cns_retry 5 10 sudo apt-get update -y
}

_cns_install_prereqs() {
  _cns_apt_get_update
  _cns_retry 3 5 sudo apt-get install -y ca-certificates curl gnupg git jq openssl
}

_cns_docker_apt_diagnostics() {
  echo "=== /etc/apt/sources.list.d/docker.list ==="
  sudo cat /etc/apt/sources.list.d/docker.list 2>/dev/null || true
  echo "=== /etc/apt/keyrings ==="
  sudo ls -la /etc/apt/keyrings 2>/dev/null || true
  echo "=== tail /var/log/cloud-init-output.log ==="
  sudo tail -n 200 /var/log/cloud-init-output.log 2>/dev/null || true
}

_cns_write_docker_apt_repo() {
  sudo rm -f /etc/apt/sources.list.d/docker.list
  sudo install -m 0755 -d /etc/apt/keyrings
  _cns_retry 5 10 curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  _cns_log "Wrote /etc/apt/sources.list.d/docker.list:"
  sudo cat /etc/apt/sources.list.d/docker.list
}

_cns_install_docker_via_apt() {
  _cns_install_prereqs
  _cns_write_docker_apt_repo
  _cns_apt_get_update
  _cns_retry 3 10 sudo apt-get install -y \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}

_cns_install_docker_via_getdocker() {
  _cns_install_prereqs
  _cns_retry 3 15 bash -c 'curl -fsSL https://get.docker.com | sh'
  _cns_retry 3 10 sudo apt-get install -y docker-compose-plugin || true
}

_cns_enable_docker_service() {
  sudo systemctl enable docker
  sudo systemctl start docker
  if id ubuntu >/dev/null 2>&1; then
    sudo usermod -aG docker ubuntu || true
  fi
  if [[ -n "${USER:-}" ]] && [[ "${USER}" != "root" ]]; then
    sudo usermod -aG docker "${USER}" || true
  fi
}

_cns_docker_bin() {
  if command -v docker >/dev/null 2>&1; then
    echo docker
  elif sudo command -v docker >/dev/null 2>&1; then
    echo "sudo docker"
  else
    return 1
  fi
}

_cns_docker_ready() {
  local docker_bin
  docker_bin="$(_cns_docker_bin)" || return 1
  # shellcheck disable=SC2086
  ${docker_bin} --version >/dev/null 2>&1 || return 1
  # shellcheck disable=SC2086
  ${docker_bin} compose version >/dev/null 2>&1 || return 1
  [[ "$(systemctl is-active docker 2>/dev/null || echo inactive)" == "active" ]] || return 1
  return 0
}

_cns_install_docker_if_needed() {
  if _cns_docker_ready; then
    _cns_log "Docker already available"
    return 0
  fi
  _cns_log "Installing Docker via apt..."
  if _cns_install_docker_via_apt; then
    _cns_enable_docker_service
    return 0
  fi
  _cns_log "apt Docker install failed; trying get.docker.com"
  _cns_docker_apt_diagnostics
  _cns_install_docker_via_getdocker
  _cns_enable_docker_service
}

_cns_wait_for_docker() {
  local deadline=$((SECONDS + CNS_DOCKER_WAIT_SECONDS))
  local n=1
  while (( SECONDS < deadline )); do
    if _cns_docker_ready; then
      local docker_bin
      docker_bin="$(_cns_docker_bin)"
      _cns_log "Docker ready (attempt ${n})"
      # shellcheck disable=SC2086
      ${docker_bin} --version
      # shellcheck disable=SC2086
      ${docker_bin} compose version
      systemctl is-active docker
      return 0
    fi
    _cns_log "Waiting for Docker (${n}, $((deadline - SECONDS))s remaining)..."
    if ! command -v docker >/dev/null 2>&1 && ! sudo command -v docker >/dev/null 2>&1; then
      _cns_install_docker_if_needed || true
    else
      _cns_enable_docker_service || true
    fi
    sleep 5
    n=$((n + 1))
  done
  _cns_cloud_init_report
  _cns_docker_apt_diagnostics
  _cns_die "Docker not available after ${CNS_DOCKER_WAIT_SECONDS}s"
}

ec2_bootstrap_host() {
  _cns_wait_for_cloud_init
  _cns_install_docker_if_needed
  _cns_wait_for_docker
}

if [[ "${BASH_SOURCE[0]:-}" == "${0}" ]]; then
  ec2_bootstrap_host
fi
