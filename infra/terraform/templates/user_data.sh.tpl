#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

log() { echo "[cns-user-data] $*"; }
die() { log "FATAL: $*"; exit 1; }

retry() {
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
    log "Attempt $${n}/$${attempts} failed; retrying in $${delay}s: $*"
    sleep "$delay"
    n=$((n + 1))
  done
}

apt_get_update() {
  retry 5 10 apt-get update -y
}

install_prereqs() {
  apt_get_update
  retry 3 5 apt-get install -y ca-certificates curl gnupg git jq openssl
}

install_docker_via_apt() {
  install_prereqs
  rm -f /etc/apt/sources.list.d/docker.list
  install -m 0755 -d /etc/apt/keyrings
  retry 5 10 curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  ARCH="$$(dpkg --print-architecture)"
  # shellcheck disable=SC1091
  . /etc/os-release
  UBUNTU_CODENAME="$${VERSION_CODENAME:-noble}"
  echo "ARCH=$${ARCH}"
  echo "UBUNTU_CODENAME=$${UBUNTU_CODENAME}"
  cat /etc/os-release || true
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' "$${ARCH}" "$${UBUNTU_CODENAME}" \
    > /etc/apt/sources.list.d/docker.list
  log "Wrote /etc/apt/sources.list.d/docker.list:"
  cat /etc/apt/sources.list.d/docker.list
  validate_docker_apt_list || die "invalid /etc/apt/sources.list.d/docker.list (arch/codename/signed-by)"
  apt_get_update
  retry 3 10 apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}

validate_docker_apt_list() {
  grep -Eq '^deb \[arch=(amd64|arm64) signed-by=/etc/apt/keyrings/docker.asc\] https://download.docker.com/linux/ubuntu (noble|jammy|focal) stable$$' \
    /etc/apt/sources.list.d/docker.list
}

docker_apt_diagnostics() {
  log "Docker apt diagnostics:"
  cat /etc/os-release || true
  echo "ARCH=$${ARCH:-unknown}"
  echo "UBUNTU_CODENAME=$${UBUNTU_CODENAME:-unknown}"
  cat /etc/apt/sources.list.d/docker.list || true
  ls -la /etc/apt/keyrings || true
  tail -n 200 /var/log/cloud-init-output.log || true
}

install_docker_via_getdocker() {
  install_prereqs
  retry 3 15 bash -c 'curl -fsSL https://get.docker.com | sh'
  retry 3 10 apt-get install -y docker-compose-plugin || true
}

enable_docker_service() {
  systemctl enable docker
  systemctl start docker
  if id ubuntu >/dev/null 2>&1; then
    usermod -aG docker ubuntu || true
  fi
}

verify_docker() {
  docker --version
  docker compose version
  [[ "$$(systemctl is-active docker)" == "active" ]]
}

log "Installing Docker Engine..."
if install_docker_via_apt; then
  log "Docker installed via apt"
else
  log "apt Docker install failed; trying get.docker.com"
  docker_apt_diagnostics
  install_docker_via_getdocker || { docker_apt_diagnostics; die "get.docker.com install failed"; }
fi

enable_docker_service || { docker_apt_diagnostics; die "failed to enable/start docker service"; }
verify_docker || { docker_apt_diagnostics; die "Docker verification failed after install"; }

log "Docker bootstrap completed successfully"

%{ if staging_bootstrap ~}
# Staging bootstrap: seed .env.staging before first GitHub Actions deploy (cloud-init only runs once).
STAGING_DIR="/home/ubuntu/cloud-networking-studio-staging"
install -d -m 0750 -o ubuntu -g ubuntu "$${STAGING_DIR}"
if [[ ! -f "$${STAGING_DIR}/.env.staging" ]]; then
  umask 077
  cat > "$${STAGING_DIR}/.env.staging" <<STAGING_ENV
CNS_ENVIRONMENT=staging
CNS_CORS_ORIGINS=${staging_cors_origins}
CNS_CADDY_SITE_ADDRESS=${staging_api_host}
SSLIP_HOST=${staging_api_host}
CNS_SSLIP_HOST=${staging_api_host}
CADDYFILE_CADDY=./deploy/Caddyfile.staging-https
CNS_CADDY_AUTO_HTTPS=on
CNS_FRONTEND_APP_URL=${staging_app_url}
STAGING_ENV
  chown ubuntu:ubuntu "$${STAGING_DIR}/.env.staging"
  chmod 0600 "$${STAGING_DIR}/.env.staging"
  log "Wrote staging bootstrap $${STAGING_DIR}/.env.staging"
fi
%{ endif ~}
