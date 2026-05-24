#!/bin/bash
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl gnupg git jq

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
. /etc/os-release
echo "deb [arch=$$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable docker
systemctl start docker
if id ubuntu >/dev/null 2>&1; then
  usermod -aG docker ubuntu || true
fi

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
fi
%{ endif ~}
