#!/usr/bin/env bash
# Deploy the production Docker stack on EC2.
# Invoked from .github/workflows/deploy-production.yml over SSH after checkout.
#
# Required env (set by workflow; secrets are not echoed):
#   GIT_SHA, GITHUB_REPOSITORY, GITHUB_TOKEN
#   POSTGRES_PASSWORD, CNS_CORS_ORIGINS, CNS_CADDY_SITE_ADDRESS
#
# Optional env:
#   RDS_ENDPOINT, RDS_PORT, RDS_DATABASE_NAME, RDS_USERNAME, RDS_PASSWORD
#   CNS_LEGACY_SSLIP_HTTP, AUTH_SECRET_KEY
#   RUNTIME_EXECUTOR, RUNTIME_PROVIDER, GO_RUNNER_URL
#   GOOGLE_APPLICATION_CREDENTIALS, CNS_REMOTE_DOCKER_SSH_KEY_PATH, CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra_deployment_credentials.sh
source "${SCRIPT_DIR}/infra_deployment_credentials.sh"

REPO_DIR="${HOME}/cloud-networking-studio"
ENV_FILE=".env"
COMPOSE=(sudo docker compose)
C_ARGS=(-f docker-compose.prod.yml -f docker-compose.caddy-https.yml --env-file "${ENV_FILE}")

if [[ -z "${GIT_SHA:-}" ]] || [[ -z "${GITHUB_REPOSITORY:-}" ]] || [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "::error::prod_deploy_remote.sh: GIT_SHA, GITHUB_REPOSITORY, and GITHUB_TOKEN are required."
  exit 1
fi

gen_secret_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets; print(secrets.token_hex(32))'
  else
    ( set +o pipefail; LC_ALL=C tr -dc 'a-f0-9' </dev/urandom | head -c 64 )
  fi
}

run_compose() {
  prepare_compose_interpolation_env
  if [[ "${CNS_CADDY_AUTO_HTTPS:-}" == "on" ]]; then
    local saw_down=0 arg
    for arg in "$@"; do
      if [[ "${arg}" == "down" ]]; then
        saw_down=1
      fi
    done
    if [[ "${saw_down}" -eq 1 ]]; then
      for arg in "$@"; do
        if [[ "${arg}" == "-v" ]] || [[ "${arg}" == "--volumes" ]]; then
          echo "::error::Refusing docker compose down with volume removal (-v/--volumes) when CNS_CADDY_AUTO_HTTPS=on (deletes caddy_data/caddy_config; new LE certs → rate limits). Use docker compose down without -v/--volumes. See docs/CICD_DEPLOYMENT.md."
          exit 1
        fi
      done
    fi
  fi
  "${COMPOSE[@]}" "$@"
}

curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  "https://raw.githubusercontent.com/${GITHUB_REPOSITORY}/${GIT_SHA}/scripts/ec2_bootstrap_docker.sh" \
  -o /tmp/ec2_bootstrap_docker.sh
# shellcheck source=/dev/null
source /tmp/ec2_bootstrap_docker.sh
ec2_bootstrap_host

set +x
echo "=== git clone / fetch / checkout (xtrace off — secrets) ==="
REPO_SLUG="${GITHUB_REPOSITORY}"
TOKEN="${GITHUB_TOKEN}"
CLONE_URL="https://x-access-token:${TOKEN}@github.com/${REPO_SLUG}.git"
if [[ ! -d "${REPO_DIR}/.git" ]]; then
  git clone "${CLONE_URL}" "${REPO_DIR}"
fi
cd "${REPO_DIR}"
git remote set-url origin "${CLONE_URL}"
git fetch origin
git checkout "${GIT_SHA}"
git rev-parse HEAD
git status --short || true

echo "=== write production ${ENV_FILE} (values not printed) ==="
ENV_PATH="${REPO_DIR}/${ENV_FILE}"
EXISTING_ENV=""
if [[ -f "${ENV_PATH}" ]]; then
  EXISTING_ENV="${ENV_PATH}"
fi

echo "POSTGRES_PASSWORD present? $([[ -n "${POSTGRES_PASSWORD:-}" ]] && echo yes || echo no)"
echo "RDS_PASSWORD present? $([[ -n "${RDS_PASSWORD:-}" ]] && echo yes || echo no)"
echo "RDS_ENDPOINT present? $([[ -n "${RDS_ENDPOINT:-}" ]] && echo yes || echo no)"
echo "CNS_CORS_ORIGINS present? $([[ -n "${CNS_CORS_ORIGINS:-}" ]] && echo yes || echo no)"
echo "AUTH_SECRET_KEY present? $([[ -n "${AUTH_SECRET_KEY:-}" ]] && echo yes || echo no)"

AUTH_SECRET_KEY="$(printf '%s' "${AUTH_SECRET_KEY:-}" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
if [[ -z "${AUTH_SECRET_KEY}" ]] && [[ -n "${EXISTING_ENV}" ]]; then
  AUTH_SECRET_KEY="$(read_env_value AUTH_SECRET_KEY "${EXISTING_ENV}" || true)"
  AUTH_SECRET_KEY="$(printf '%s' "${AUTH_SECRET_KEY}" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
fi
CNS_DEV_AUTH_DEFAULT="local-dev-only-change-AUTH_SECRET_KEY-in-production-min-32-chars"
if [[ -z "${AUTH_SECRET_KEY}" ]] || [[ "${AUTH_SECRET_KEY}" == "${CNS_DEV_AUTH_DEFAULT}" ]]; then
  AUTH_SECRET_KEY="$(gen_secret_hex)"
fi
if [[ -z "${AUTH_SECRET_KEY}" ]] || [[ ${#AUTH_SECRET_KEY} -lt 32 ]]; then
  echo "::error::Production AUTH_SECRET_KEY material was empty or too short after resolution."
  exit 1
fi

PUB_HOST="$(printf '%s' "${CNS_CADDY_SITE_ADDRESS:-}" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
if [[ -z "${PUB_HOST}" ]]; then
  echo "::error::SSH deploy: CNS_CADDY_SITE_ADDRESS empty after trim."
  exit 1
fi
if [[ -z "${POSTGRES_PASSWORD:-}" ]] || [[ -z "${CNS_CORS_ORIGINS:-}" ]]; then
  echo "::error::SSH deploy: POSTGRES_PASSWORD or CNS_CORS_ORIGINS empty on remote."
  exit 1
fi

CNS_REQUIRED_CORS_ORIGINS="https://app.cloudnetstudio.com,http://${PUB_HOST},https://${PUB_HOST}"
if [[ -n "${CNS_LEGACY_SSLIP_HTTP:-}" ]]; then
  CNS_REQUIRED_CORS_ORIGINS="${CNS_REQUIRED_CORS_ORIGINS},${CNS_LEGACY_SSLIP_HTTP}"
fi
CNS_CORS_ORIGINS="${CNS_CORS_ORIGINS},${CNS_REQUIRED_CORS_ORIGINS}"

CNS_CADDY_SITE_ADDRESS="${PUB_HOST}"
CNS_CADDY_AUTO_HTTPS="${CNS_CADDY_AUTO_HTTPS:-on}"
CADDYFILE_CADDY="${CADDYFILE_CADDY:-./deploy/Caddyfile.public-https}"
CNS_ENVIRONMENT="${CNS_ENVIRONMENT:-production}"
CNS_CONTROLLER_MODE="${CNS_CONTROLLER_MODE:-manual}"
RUNTIME_EXECUTOR="${RUNTIME_EXECUTOR:-go}"
RUNTIME_PROVIDER="${RUNTIME_PROVIDER:-docker}"
GO_RUNNER_URL="${GO_RUNNER_URL:-http://runner:8090}"

RDS_EP="$(printf '%s' "${RDS_ENDPOINT:-}" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
RDS_P="$(printf '%s' "${RDS_PORT:-}" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
if [[ -z "${RDS_P}" ]]; then RDS_P="5432"; fi
RDS_USER="$(printf '%s' "${RDS_USERNAME:-cns_user}" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
RDS_DB="$(printf '%s' "${RDS_DATABASE_NAME:-cloud_networking_studio}" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

DATABASE_URL=""
if [[ -n "${RDS_EP}" ]] && command -v python3 >/dev/null 2>&1; then
  export _CNS_PY_HOST="${RDS_EP}"
  export _CNS_PY_PORT="${RDS_P}"
  export _CNS_PY_USER="${RDS_USER}"
  export _CNS_PY_DB="${RDS_DB}"
  export _CNS_PY_PW="${POSTGRES_PASSWORD}"
  set +e
  PYOUT="$(python3 -c 'import os,urllib.parse as u;h=os.environ["_CNS_PY_HOST"].strip();pt=(os.environ.get("_CNS_PY_PORT") or "5432").strip() or "5432";user=u.quote(os.environ["_CNS_PY_USER"].strip(),safe="");pw=u.quote(os.environ["_CNS_PY_PW"],safe="");db=os.environ["_CNS_PY_DB"].strip();print("postgresql://"+user+":"+pw+"@"+h+":"+pt+"/"+db)' 2>/dev/null)"
  PYRC=$?
  set -e
  unset _CNS_PY_HOST _CNS_PY_PORT _CNS_PY_USER _CNS_PY_DB _CNS_PY_PW || true
  if [[ "${PYRC}" -eq 0 ]] && [[ -n "${PYOUT}" ]]; then
    DATABASE_URL="${PYOUT}"
  else
    echo "::warning::Could not build RDS DATABASE_URL (python rc=${PYRC}); using Docker Postgres service."
  fi
elif [[ -n "${RDS_EP}" ]]; then
  echo "::warning::RDS_ENDPOINT set but python3 not found; using Docker Postgres service."
fi
if [[ -z "${DATABASE_URL}" ]]; then
  DATABASE_URL="postgresql://cns_user:${POSTGRES_PASSWORD}@postgres:5432/cloud_networking_studio"
fi

if [[ "${DATABASE_URL}" == *"@postgres:"* ]]; then
  DB_MODE="localdb"
else
  DB_MODE="external"
fi
echo "database mode: ${DB_MODE}"

CNS_REMOTE_DOCKER_SSH_KEY_PATH="$(resolve_cns_remote_docker_ssh_key_path "${EXISTING_ENV}")"
CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH="$(resolve_cns_remote_docker_ssh_public_key_path "${EXISTING_ENV}")"
GOOGLE_APPLICATION_CREDENTIALS="$(resolve_google_application_credentials_path "${EXISTING_ENV}")"

sudo install -d -m 0750 -o "${USER}" -g "${USER}" "${SECRETS_DIR}" 2>/dev/null || sudo install -d -m 0750 "${SECRETS_DIR}"

umask 077
{
  printf '%s\n' \
    "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" \
    "CNS_CORS_ORIGINS=${CNS_CORS_ORIGINS}" \
    "CNS_ENVIRONMENT=${CNS_ENVIRONMENT}" \
    "CNS_CONTROLLER_MODE=${CNS_CONTROLLER_MODE}" \
    "CNS_CADDY_SITE_ADDRESS=${CNS_CADDY_SITE_ADDRESS}" \
    "CNS_CADDY_AUTO_HTTPS=${CNS_CADDY_AUTO_HTTPS}" \
    "DATABASE_URL=${DATABASE_URL}" \
    "SSLIP_HOST=${PUB_HOST}" \
    "CNS_SSLIP_HOST=${PUB_HOST}" \
    "CADDYFILE_CADDY=${CADDYFILE_CADDY}" \
    "AUTH_REQUIRE_LOGIN=true" \
    "AUTH_SECRET_KEY=${AUTH_SECRET_KEY}" \
    "RUNTIME_EXECUTOR=${RUNTIME_EXECUTOR}" \
    "RUNTIME_PROVIDER=${RUNTIME_PROVIDER}" \
    "GO_RUNNER_URL=${GO_RUNNER_URL}" \
    "GOOGLE_APPLICATION_CREDENTIALS=${GOOGLE_APPLICATION_CREDENTIALS}" \
    "CNS_REMOTE_DOCKER_SSH_KEY_PATH=${CNS_REMOTE_DOCKER_SSH_KEY_PATH}" \
    "CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH=${CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH}"
} > "${ENV_FILE}"

ensure_infra_deployment_credential_env_lines

echo "=== production ${ENV_FILE} written (keys only) ==="
cut -d= -f1 "${ENV_FILE}"
echo "=== production infra credential paths (safe debug) ==="
grep -E '^(GOOGLE_APPLICATION_CREDENTIALS|CNS_REMOTE_DOCKER_SSH_KEY_PATH|CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH)=' "${ENV_FILE}" || true

verify_host_infra_credential_files

unset TOKEN CLONE_URL POSTGRES_PASSWORD RDS_PASSWORD CNS_CORS_ORIGINS CNS_LEGACY_SSLIP_HTTP DATABASE_URL RDS_ENDPOINT RDS_PORT RDS_DATABASE_NAME RDS_USERNAME AUTH_SECRET_KEY || true
set -x

echo "=== docker compose config ==="
if ! run_compose "${C_ARGS[@]}" config; then
  run_compose "${C_ARGS[@]}" ps -a || true
  run_compose "${C_ARGS[@]}" logs --tail=120 || true
  exit 1
fi
verify_rendered_compose_gcp_credentials run_compose "${C_ARGS[@]}"
verify_rendered_compose_ssh_credentials run_compose "${C_ARGS[@]}"

echo "=== docker compose down (no -v: keeps postgres_data, caddy_data, caddy_config) ==="
run_compose "${C_ARGS[@]}" down || true

echo "=== docker compose up -d --build --remove-orphans ==="
if ! run_compose "${C_ARGS[@]}" up -d --build --remove-orphans; then
  run_compose "${C_ARGS[@]}" ps -a || true
  run_compose "${C_ARGS[@]}" logs --tail=120 || true
  exit 1
fi

echo "=== restart production backend + runner (reload ${ENV_FILE}) ==="
if ! run_compose "${C_ARGS[@]}" up -d --force-recreate --no-deps backend runner; then
  run_compose "${C_ARGS[@]}" logs backend --tail=120 || true
  run_compose "${C_ARGS[@]}" logs runner --tail=120 || true
  exit 1
fi

echo "=== docker volume ls (caddy TLS volumes — never docker volume rm in production) ==="
sudo docker volume ls | grep -i caddy || true

echo "=== docker compose ps ==="
run_compose "${C_ARGS[@]}" ps

echo "=== production infra credentials (backend + runner; no secret contents) ==="
verify_infra_credentials_in_containers run_compose "${C_ARGS[@]}"

echo "=== alembic upgrade head (before smoke / health gate) ==="
if ! run_compose "${C_ARGS[@]}" exec -T backend alembic upgrade head; then
  run_compose "${C_ARGS[@]}" logs backend --tail=120 || true
  exit 1
fi

echo "=== runner RUNTIME_PROVIDER (container env) ==="
run_compose "${C_ARGS[@]}" exec -T runner env | grep RUNTIME_PROVIDER || true

echo "=== backend runtime executor (container env) ==="
run_compose "${C_ARGS[@]}" exec -T backend env | grep -E 'RUNTIME_EXECUTOR|GO_RUNNER_URL' || true

echo "=== docker compose logs caddy (tail=80) ==="
run_compose "${C_ARGS[@]}" logs caddy --tail=80 || true

echo "=== EC2-local backend /health (debug fallback — blocking check is runner HTTPS prod_smoke_test.sh) ==="
EC2_LOCAL_OK=0
for attempt in $(seq 1 30); do
  if run_compose "${C_ARGS[@]}" exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health').read()" >/dev/null 2>&1; then
    echo "EC2-local backend /health OK (attempt ${attempt})"
    EC2_LOCAL_OK=1
    break
  fi
  echo "Waiting for backend /health on EC2 (attempt ${attempt}/30)..."
  sleep 2
done
if [[ "${EC2_LOCAL_OK}" -ne 1 ]]; then
  echo "::warning::EC2-local backend /health failed (non-blocking). GitHub runner prod_smoke_test.sh against HTTPS is authoritative."
  run_compose "${C_ARGS[@]}" ps -a || true
  run_compose "${C_ARGS[@]}" logs backend --tail=80 || true
fi
