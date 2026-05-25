#!/usr/bin/env bash
# Deploy the staging Docker stack on EC2 (Step 55).
# Invoked from .github/workflows/deploy-staging.yml over SSH after checkout.
#
# Required env (set by workflow; secrets are not echoed):
#   CHECKOUT_REF          git SHA / branch to deploy
#   GITHUB_REPOSITORY     owner/repo
#   GITHUB_TOKEN          clone token
#
# Optional env:
#   CNS_STAGING_API_HOST  default api-staging.cloudnetstudio.com
#   CNS_STAGING_APP_URL   default https://app-staging.cloudnetstudio.com
#   STAGING_AUTH_SECRET_KEY
#   STAGING_POSTGRES_PASSWORD
#   STAGING_DATABASE_URL  explicit DSN (never production RDS unless you intend to)
#   CNS_STAGING_CORS_ORIGINS  extra browser origins (merged with required staging defaults)
#   CNS_STAGING_CADDY_HTTP_PORT / CNS_STAGING_CADDY_HTTPS_PORT (co-located hosts)
#   CNS_STAGING_POSTGRES_HOST_PORT
#   STAGING_REMOTE_DOCKER_SSH_KEY_PATH  override host path (default /opt/cns/secrets/remote_docker_ssh.pem)

set -euo pipefail

REPO_DIR="${HOME}/cloud-networking-studio-staging"
PROD_DIR="${HOME}/cloud-networking-studio"
ENV_FILE=".env.staging"
LEGACY_ENV_FILE=".env"
DEFAULT_REMOTE_DOCKER_SSH_KEY_PATH="/opt/cns/secrets/remote_docker_ssh.pem"
SECRETS_DIR="/opt/cns/secrets"
COMPOSE=(sudo docker compose)
C_ARGS=(-f docker-compose.prod.yml -f docker-compose.caddy-https.yml -f docker-compose.staging.yml --env-file "${ENV_FILE}")

STAGING_API_HOST="$(printf '%s' "${CNS_STAGING_API_HOST:-api-staging.cloudnetstudio.com}" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
STAGING_API_HOST="${STAGING_API_HOST#https://}"
STAGING_API_HOST="${STAGING_API_HOST#http://}"
STAGING_API_HOST="${STAGING_API_HOST%%/*}"

STAGING_APP_URL="$(printf '%s' "${CNS_STAGING_APP_URL:-https://app-staging.cloudnetstudio.com}" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

if [[ -z "${CHECKOUT_REF:-}" ]] || [[ -z "${GITHUB_REPOSITORY:-}" ]] || [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "::error::staging_deploy_remote.sh: CHECKOUT_REF, GITHUB_REPOSITORY, and GITHUB_TOKEN are required."
  exit 1
fi

if [[ -z "${STAGING_API_HOST}" ]]; then
  echo "::error::CNS_STAGING_API_HOST is empty after normalization."
  exit 1
fi

normalize_checkout_ref() {
  local ref="$1"
  ref="$(printf '%s' "$ref" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  printf '%s' "$ref"
}

print_git_diagnostics() {
  echo "=== git diagnostics ==="
  git branch -a || true
  git status --short || true
  git rev-parse --abbrev-ref HEAD || true
  git rev-parse --short HEAD || true
}

checkout_deploy_ref() {
  local ref
  ref="$(normalize_checkout_ref "$1")"
  if [[ -z "${ref}" ]]; then
    echo "::error::CHECKOUT_REF is empty after normalization."
    return 1
  fi

  git fetch origin --tags --prune

  # Detached commit SHA (full or short).
  if [[ "${ref}" =~ ^[0-9a-fA-F]{7,40}$ ]]; then
    git fetch origin "${ref}"
    git checkout --detach "${ref}"
    return 0
  fi

  # Annotated/lightweight tag by full ref.
  if [[ "${ref}" == refs/tags/* ]]; then
    local tag="${ref#refs/tags/}"
    git fetch origin "refs/tags/${tag}"
    git checkout --detach "refs/tags/${tag}" 2>/dev/null || git checkout -B "${tag}" "origin/${tag}"
    return 0
  fi

  # Branch: refs/heads/name, origin/name, or bare name — never checkout refs/heads/* directly.
  local branch="${ref}"
  branch="${branch#refs/heads/}"
  branch="${branch#origin/}"

  git fetch origin "${branch}"
  if git show-ref --verify --quiet "refs/remotes/origin/${branch}"; then
    git checkout -B "${branch}" "origin/${branch}"
    return 0
  fi

  echo "::error::Could not resolve '${branch}' — origin/${branch} missing after fetch."
  print_git_diagnostics
  return 1
}

# --- Safety: never mutate production stack paths or secrets ---
if [[ -n "${COMPOSE_PROJECT_NAME:-}" ]] && [[ "${COMPOSE_PROJECT_NAME}" == "cns-prod" ]]; then
  echo "::error::Refusing deploy: COMPOSE_PROJECT_NAME=cns-prod on staging script."
  exit 1
fi

if [[ -n "${CNS_ENVIRONMENT:-}" ]] && [[ "${CNS_ENVIRONMENT}" == "production" ]]; then
  echo "::error::Refusing deploy: CNS_ENVIRONMENT=production on staging script."
  exit 1
fi

run_ec2_bootstrap_host() {
  local script=""
  if [[ -f "${REPO_DIR}/scripts/ec2_bootstrap_docker.sh" ]]; then
    script="${REPO_DIR}/scripts/ec2_bootstrap_docker.sh"
  elif [[ -n "${GITHUB_TOKEN:-}" ]] && [[ -n "${GITHUB_REPOSITORY:-}" ]] && [[ -n "${CHECKOUT_REF:-}" ]]; then
    script="/tmp/ec2_bootstrap_docker.sh"
    if ! curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN}" \
      "https://raw.githubusercontent.com/${GITHUB_REPOSITORY}/${CHECKOUT_REF}/scripts/ec2_bootstrap_docker.sh" \
      -o "${script}"; then
      script=""
    fi
  fi
  if [[ -z "${script}" ]] || [[ ! -f "${script}" ]]; then
    echo "::error::Could not load scripts/ec2_bootstrap_docker.sh for host bootstrap."
    exit 1
  fi
  # shellcheck source=/dev/null
  source "${script}"
  ec2_bootstrap_host
}

gen_secret_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets; print(secrets.token_hex(32))'
  else
    ( set +o pipefail; LC_ALL=C tr -dc 'a-f0-9' </dev/urandom | head -c 64 )
  fi
}

read_env_value() {
  local key="$1"
  local file="$2"
  local line val
  [[ -f "${file}" ]] || return 1
  line="$(grep -E "^${key}=" "${file}" | tail -n1 || true)"
  [[ -n "${line}" ]] || return 1
  val="${line#*=}"
  printf '%s' "${val}" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

merge_cors_origins() {
  local merged="" part
  declare -A seen=()
  local chunk
  for chunk in "$@"; do
    [[ -z "${chunk}" ]] && continue
    local IFS=','
    read -ra PARTS <<< "${chunk}"
    for part in "${PARTS[@]}"; do
      part="$(printf '%s' "${part}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
      [[ -z "${part}" ]] && continue
      if [[ -z "${seen[${part}]:-}" ]]; then
        seen["${part}"]=1
        if [[ -z "${merged}" ]]; then
          merged="${part}"
        else
          merged="${merged},${part}"
        fi
      fi
    done
  done
  printf '%s' "${merged}"
}

run_compose() {
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
          echo "::error::Refusing docker compose down with -v when CNS_CADDY_AUTO_HTTPS=on (staging TLS volumes)."
          exit 1
        fi
      done
    fi
  fi
  "${COMPOSE[@]}" "$@"
}

run_ec2_bootstrap_host

set +x
echo "=== git clone / fetch / checkout (staging dir; xtrace off — token in clone URL) ==="
REPO_SLUG="${GITHUB_REPOSITORY}"
CHECKOUT_REF="${CHECKOUT_REF}"
TOKEN="${GITHUB_TOKEN}"
CLONE_URL="https://x-access-token:${TOKEN}@github.com/${REPO_SLUG}.git"

if [[ ! -d "${REPO_DIR}/.git" ]]; then
  git clone "${CLONE_URL}" "${REPO_DIR}"
fi
cd "${REPO_DIR}"
git remote set-url origin "${CLONE_URL}"
if ! checkout_deploy_ref "${CHECKOUT_REF}"; then
  exit 1
fi
print_git_diagnostics
git rev-parse HEAD

echo "=== write staging ${ENV_FILE} (values not printed) ==="

ENV_PATH="${REPO_DIR}/${ENV_FILE}"
LEGACY_PATH="${REPO_DIR}/${LEGACY_ENV_FILE}"
EXISTING_ENV=""
if [[ -f "${ENV_PATH}" ]]; then
  EXISTING_ENV="${ENV_PATH}"
elif [[ -f "${LEGACY_PATH}" ]]; then
  EXISTING_ENV="${LEGACY_PATH}"
fi

gen_pg_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 24
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets; print(secrets.token_hex(24))'
  else
    ( set +o pipefail; LC_ALL=C tr -dc 'a-f0-9' </dev/urandom | head -c 48 )
  fi
}

AUTH_SECRET_KEY="$(printf '%s' "${STAGING_AUTH_SECRET_KEY:-}" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
if [[ -z "${AUTH_SECRET_KEY}" ]] && [[ -n "${EXISTING_ENV}" ]]; then
  AUTH_SECRET_KEY="$(read_env_value AUTH_SECRET_KEY "${EXISTING_ENV}" || true)"
fi
CNS_DEV_AUTH_DEFAULT="local-dev-only-change-AUTH_SECRET_KEY-in-production-min-32-chars"
if [[ -z "${AUTH_SECRET_KEY}" ]] || [[ "${AUTH_SECRET_KEY}" == "${CNS_DEV_AUTH_DEFAULT}" ]]; then
  AUTH_SECRET_KEY="$(gen_secret_hex)"
fi
if [[ -z "${AUTH_SECRET_KEY}" ]] || [[ ${#AUTH_SECRET_KEY} -lt 32 ]]; then
  echo "::error::Staging AUTH_SECRET_KEY material was empty or too short."
  exit 1
fi

POSTGRES_PASSWORD="$(printf '%s' "${STAGING_POSTGRES_PASSWORD:-}" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
if [[ -z "${POSTGRES_PASSWORD}" ]] && [[ -n "${EXISTING_ENV}" ]]; then
  POSTGRES_PASSWORD="$(read_env_value POSTGRES_PASSWORD "${EXISTING_ENV}" || true)"
fi
if [[ -z "${POSTGRES_PASSWORD}" ]]; then
  POSTGRES_PASSWORD="$(gen_pg_hex)"
fi

DATABASE_URL="$(printf '%s' "${STAGING_DATABASE_URL:-}" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
if [[ -z "${DATABASE_URL}" ]]; then
  DATABASE_URL="postgresql://cns_user:${POSTGRES_PASSWORD}@postgres:5432/cloud_networking_studio"
fi

# Block accidental production RDS unless explicitly provided via STAGING_DATABASE_URL.
if [[ -z "${STAGING_DATABASE_URL:-}" ]] && [[ "${DATABASE_URL}" != *"@postgres:"* ]]; then
  echo "::error::Staging DATABASE_URL must use local Compose postgres unless STAGING_DATABASE_URL is set explicitly."
  exit 1
fi

DEFAULT_STAGING_CORS_ORIGINS="https://app-staging.cloudnetstudio.com,https://cloud-networking-studio.vercel.app"
EXTRA_CORS="$(printf '%s' "${CNS_STAGING_CORS_ORIGINS:-}" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
EXISTING_CORS=""
if [[ -n "${EXISTING_ENV}" ]]; then
  EXISTING_CORS="$(read_env_value CNS_CORS_ORIGINS "${EXISTING_ENV}" || true)"
fi
APP_HOST="${STAGING_APP_URL#https://}"
APP_HOST="${APP_HOST#http://}"
APP_HOST="${APP_HOST%%/*}"
BASE_CORS="https://${APP_HOST},http://${STAGING_API_HOST},https://${STAGING_API_HOST},http://127.0.0.1,http://localhost"
CNS_CORS_ORIGINS="$(merge_cors_origins "${DEFAULT_STAGING_CORS_ORIGINS}" "${EXTRA_CORS}" "${EXISTING_CORS}" "${BASE_CORS}")"

REMOTE_DOCKER_SSH_KEY_PATH="$(printf '%s' "${STAGING_REMOTE_DOCKER_SSH_KEY_PATH:-}" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
if [[ -z "${REMOTE_DOCKER_SSH_KEY_PATH}" ]] && [[ -n "${EXISTING_ENV}" ]]; then
  REMOTE_DOCKER_SSH_KEY_PATH="$(read_env_value CNS_REMOTE_DOCKER_SSH_KEY_PATH "${EXISTING_ENV}" || true)"
fi
if [[ -z "${REMOTE_DOCKER_SSH_KEY_PATH}" ]]; then
  REMOTE_DOCKER_SSH_KEY_PATH="${DEFAULT_REMOTE_DOCKER_SSH_KEY_PATH}"
fi

sudo install -d -m 0750 -o "${USER}" -g "${USER}" "${SECRETS_DIR}" 2>/dev/null || sudo install -d -m 0750 "${SECRETS_DIR}"

CNS_CADDY_SITE_ADDRESS="${STAGING_API_HOST}"
CNS_CADDY_AUTO_HTTPS="${CNS_CADDY_AUTO_HTTPS:-on}"
CADDYFILE_CADDY="${CADDYFILE_CADDY:-./deploy/Caddyfile.staging-https}"

umask 077
{
  printf '%s\n' \
    "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" \
    "DATABASE_URL=${DATABASE_URL}" \
    "CNS_ENVIRONMENT=staging" \
    "CNS_CONTROLLER_MODE=manual" \
    "CNS_CORS_ORIGINS=${CNS_CORS_ORIGINS}" \
    "CNS_CADDY_SITE_ADDRESS=${CNS_CADDY_SITE_ADDRESS}" \
    "CNS_CADDY_AUTO_HTTPS=${CNS_CADDY_AUTO_HTTPS}" \
    "SSLIP_HOST=${STAGING_API_HOST}" \
    "CNS_SSLIP_HOST=${STAGING_API_HOST}" \
    "CADDYFILE_CADDY=${CADDYFILE_CADDY}" \
    "CNS_FRONTEND_APP_URL=${STAGING_APP_URL}" \
    "AUTH_REQUIRE_LOGIN=true" \
    "AUTH_SECRET_KEY=${AUTH_SECRET_KEY}" \
    "RUNTIME_EXECUTOR=go" \
    "RUNTIME_PROVIDER=docker" \
    "GO_RUNNER_URL=http://runner:8090" \
    "CNS_REMOTE_DOCKER_SSH_KEY_PATH=${REMOTE_DOCKER_SSH_KEY_PATH}"
  if [[ -n "${CNS_STAGING_POSTGRES_HOST_PORT:-}" ]]; then
    printf '%s\n' "CNS_STAGING_POSTGRES_HOST_PORT=${CNS_STAGING_POSTGRES_HOST_PORT}"
  fi
  if [[ -n "${CNS_STAGING_CADDY_HTTP_PORT:-}" ]]; then
    printf '%s\n' "CNS_STAGING_CADDY_HTTP_PORT=${CNS_STAGING_CADDY_HTTP_PORT}"
  fi
  if [[ -n "${CNS_STAGING_CADDY_HTTPS_PORT:-}" ]]; then
    printf '%s\n' "CNS_STAGING_CADDY_HTTPS_PORT=${CNS_STAGING_CADDY_HTTPS_PORT}"
  fi
} > "${ENV_FILE}"

echo "=== staging ${ENV_FILE} written (keys only) ==="
cut -d= -f1 "${ENV_FILE}"
echo "=== staging CNS_CORS_ORIGINS (safe debug) ==="
grep -E '^CNS_CORS_ORIGINS=' "${ENV_FILE}" || true
echo "=== staging CNS_REMOTE_DOCKER_SSH_KEY_PATH (safe debug) ==="
grep -E '^CNS_REMOTE_DOCKER_SSH_KEY_PATH=' "${ENV_FILE}" || true

unset TOKEN CLONE_URL POSTGRES_PASSWORD AUTH_SECRET_KEY DATABASE_URL STAGING_AUTH_SECRET_KEY STAGING_POSTGRES_PASSWORD STAGING_DATABASE_URL REMOTE_DOCKER_SSH_KEY_PATH STAGING_REMOTE_DOCKER_SSH_KEY_PATH || true
set -x

echo "=== docker compose config (project cns-staging) ==="
if ! run_compose "${C_ARGS[@]}" config | head -n 40; then
  run_compose "${C_ARGS[@]}" ps -a || true
  run_compose "${C_ARGS[@]}" logs --tail=120 || true
  exit 1
fi

echo "=== docker compose down (staging only; no -v) ==="
run_compose "${C_ARGS[@]}" down || true

echo "=== docker compose up -d --build --remove-orphans (cns-staging) ==="
if ! run_compose "${C_ARGS[@]}" up -d --build --remove-orphans; then
  run_compose "${C_ARGS[@]}" ps -a || true
  run_compose "${C_ARGS[@]}" logs --tail=120 || true
  exit 1
fi

echo "=== restart staging backend (reload ${ENV_FILE}) ==="
if ! run_compose "${C_ARGS[@]}" up -d --force-recreate --no-deps backend; then
  run_compose "${C_ARGS[@]}" logs backend --tail=120 || true
  exit 1
fi

echo "=== staging remote_docker SSH credential debug (no secret contents) ==="
grep -E '^CNS_REMOTE_DOCKER_SSH_KEY_PATH=' "${ENV_FILE}" || true
run_compose "${C_ARGS[@]}" exec -T backend printenv | grep CNS_REMOTE_DOCKER || true
run_compose "${C_ARGS[@]}" exec -T backend sh -c \
  'if [ -n "${CNS_REMOTE_DOCKER_SSH_KEY_PATH:-}" ] && [ -r "${CNS_REMOTE_DOCKER_SSH_KEY_PATH}" ]; then echo "CNS_REMOTE_DOCKER_SSH_KEY_PATH is set and readable"; else echo "CNS_REMOTE_DOCKER_SSH_KEY_PATH missing or not readable inside backend"; fi'

echo "=== docker compose ps (staging) ==="
run_compose "${C_ARGS[@]}" ps

echo "=== alembic upgrade head (staging backend) ==="
if ! run_compose "${C_ARGS[@]}" exec -T backend alembic upgrade head; then
  run_compose "${C_ARGS[@]}" logs backend --tail=120 || true
  exit 1
fi

echo "=== staging backend /health (expect environment=staging) ==="
for attempt in $(seq 1 30); do
  if run_compose "${C_ARGS[@]}" exec -T backend python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health')); assert d.get('environment')=='staging', d; print(d)" 2>/dev/null; then
    echo "Staging backend health OK (attempt ${attempt})"
    exit 0
  fi
  echo "Waiting for staging backend /health (attempt ${attempt}/30)..."
  sleep 2
done

echo "::error::Staging backend /health did not report environment=staging."
run_compose "${C_ARGS[@]}" logs backend --tail=80 || true
exit 1
