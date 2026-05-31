#!/usr/bin/env bash
# Shared helpers for GCP infrastructure deployment credentials on EC2 hosts.
# Sourced by scripts/staging_deploy_remote.sh and scripts/prod_deploy_remote.sh.

: "${DEFAULT_REMOTE_DOCKER_SSH_KEY_PATH:=/opt/cns/secrets/gcp-remote-docker-key}"
: "${DEFAULT_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH:=/opt/cns/secrets/gcp-remote-docker-key.pub}"
: "${DEFAULT_GCP_TERRAFORM_CREDS_PATH:=/opt/cns/secrets/gcp-terraform-sa.json}"
: "${SECRETS_DIR:=/opt/cns/secrets}"

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

resolve_cns_remote_docker_ssh_key_path() {
  local existing_file="${1:-}"
  local value
  value="$(printf '%s' "${CNS_REMOTE_DOCKER_SSH_KEY_PATH:-}" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  if [[ -z "${value}" ]]; then
    value="$(printf '%s' "${STAGING_REMOTE_DOCKER_SSH_KEY_PATH:-}" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  fi
  if [[ -z "${value}" ]] && [[ -n "${existing_file}" ]] && [[ -f "${existing_file}" ]]; then
    value="$(read_env_value CNS_REMOTE_DOCKER_SSH_KEY_PATH "${existing_file}" || true)"
  fi
  if [[ -z "${value}" ]]; then
    value="${DEFAULT_REMOTE_DOCKER_SSH_KEY_PATH}"
  fi
  printf '%s' "${value}"
}

resolve_cns_remote_docker_ssh_public_key_path() {
  local existing_file="${1:-}"
  local value
  value="$(printf '%s' "${CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH:-}" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  if [[ -z "${value}" ]] && [[ -n "${existing_file}" ]] && [[ -f "${existing_file}" ]]; then
    value="$(read_env_value CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH "${existing_file}" || true)"
  fi
  if [[ -z "${value}" ]]; then
    value="${DEFAULT_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH}"
  fi
  printf '%s' "${value}"
}

resolve_google_application_credentials_path() {
  local existing_file="${1:-}"
  local value
  value="$(printf '%s' "${GOOGLE_APPLICATION_CREDENTIALS:-}" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  if [[ -z "${value}" ]] && [[ -n "${existing_file}" ]] && [[ -f "${existing_file}" ]]; then
    value="$(read_env_value GOOGLE_APPLICATION_CREDENTIALS "${existing_file}" || true)"
  fi
  if [[ -z "${value}" ]]; then
    value="${DEFAULT_GCP_TERRAFORM_CREDS_PATH}"
  fi
  printf '%s' "${value}"
}

ensure_env_line() {
  local key="$1"
  local value="$2"
  local env_file="$3"
  if [[ -z "${value}" ]]; then
    echo "::error::${key} resolved empty."
    exit 1
  fi
  grep -v "^${key}=" "${env_file}" > "${env_file}.tmp" || true
  mv "${env_file}.tmp" "${env_file}"
  echo "${key}=${value}" >> "${env_file}"
}

ensure_remote_docker_ssh_key_path_env_line() {
  ensure_env_line CNS_REMOTE_DOCKER_SSH_KEY_PATH "${CNS_REMOTE_DOCKER_SSH_KEY_PATH}" "${ENV_FILE}"
  export CNS_REMOTE_DOCKER_SSH_KEY_PATH
}

ensure_remote_docker_ssh_public_key_path_env_line() {
  ensure_env_line CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH "${CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH}" "${ENV_FILE}"
  export CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH
}

ensure_google_application_credentials_env_line() {
  ensure_env_line GOOGLE_APPLICATION_CREDENTIALS "${GOOGLE_APPLICATION_CREDENTIALS}" "${ENV_FILE}"
  export GOOGLE_APPLICATION_CREDENTIALS
}

ensure_infra_deployment_credential_env_lines() {
  ensure_remote_docker_ssh_key_path_env_line
  ensure_remote_docker_ssh_public_key_path_env_line
  ensure_google_application_credentials_env_line
}

prepare_compose_interpolation_env() {
  # Docker Compose treats empty shell variables as "set", blocking --env-file defaults.
  if [[ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]]; then
    unset GOOGLE_APPLICATION_CREDENTIALS
  fi
  if [[ -z "${CNS_REMOTE_DOCKER_SSH_KEY_PATH:-}" ]]; then
    unset CNS_REMOTE_DOCKER_SSH_KEY_PATH
  fi
  if [[ -z "${CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH:-}" ]]; then
    unset CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH
  fi
}

verify_host_infra_credential_files() {
  local path errors=0
  for path in "${GOOGLE_APPLICATION_CREDENTIALS}" "${CNS_REMOTE_DOCKER_SSH_KEY_PATH}" "${CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH}"; do
    if [[ ! -r "${path}" ]]; then
      echo "::error::Required credential file missing or not readable on host: ${path}"
      errors=$((errors + 1))
    else
      echo "Host credential file OK (readable): ${path}"
    fi
  done
  if [[ "${errors}" -gt 0 ]]; then
    exit 1
  fi
}

verify_gcp_terraform_credentials_in_container() {
  local service="$1"
  shift
  local label="${service}="
  if ! "$@" exec -T "${service}" sh -lc '
    label="'"${label}"'"
    if [ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]; then
      echo "${label}"
      echo "GOOGLE_APPLICATION_CREDENTIALS is not configured in '"${service}"' container."
      exit 1
    fi
    echo "${label}${GOOGLE_APPLICATION_CREDENTIALS}"
    if ! test -r "${GOOGLE_APPLICATION_CREDENTIALS}"; then
      echo "GOOGLE_APPLICATION_CREDENTIALS file is not readable in '"${service}"' container."
      exit 1
    fi
    if [ "'"${service}"'" = "backend" ]; then
      echo BACKEND_GCP_CREDS_READABLE
    else
      echo RUNNER_GCP_CREDS_READABLE
    fi
  '; then
    echo "::error::GCP Terraform credentials verification failed for ${service}."
    exit 1
  fi
}

verify_remote_docker_ssh_credentials_in_container() {
  local service="$1"
  shift
  if ! "$@" exec -T "${service}" sh -lc '
    if [ -z "${CNS_REMOTE_DOCKER_SSH_KEY_PATH:-}" ]; then
      echo "CNS_REMOTE_DOCKER_SSH_KEY_PATH is not configured in '"${service}"' container."
      exit 1
    fi
    echo "CNS_REMOTE_DOCKER_SSH_KEY_PATH=${CNS_REMOTE_DOCKER_SSH_KEY_PATH}"
    if ! test -r "${CNS_REMOTE_DOCKER_SSH_KEY_PATH}"; then
      echo "CNS_REMOTE_DOCKER_SSH_KEY_PATH file is not readable in '"${service}"' container."
      exit 1
    fi
    if [ -z "${CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH:-}" ]; then
      echo "CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH is not configured in '"${service}"' container."
      exit 1
    fi
    echo "CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH=${CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH}"
    if ! test -r "${CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH}"; then
      echo "CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH file is not readable in '"${service}"' container."
      exit 1
    fi
    echo "'"${service}"'_SSH_CREDS_READABLE"
  '; then
    echo "::error::Remote Docker SSH credentials verification failed for ${service}."
    exit 1
  fi
}

verify_rendered_compose_gcp_credentials() {
  local cfg count
  cfg="$("$@" config 2>/dev/null || true)"
  count="$(printf '%s\n' "${cfg}" | grep -c "GOOGLE_APPLICATION_CREDENTIALS: ${GOOGLE_APPLICATION_CREDENTIALS}" || true)"
  if [[ "${count}" -lt 2 ]]; then
    echo "::error::Rendered compose config missing GOOGLE_APPLICATION_CREDENTIALS for backend and/or runner."
    printf '%s\n' "${cfg}" | grep GOOGLE_APPLICATION_CREDENTIALS || true
    exit 1
  fi
  echo "Rendered compose config: GOOGLE_APPLICATION_CREDENTIALS present for backend and runner"
}

verify_rendered_compose_ssh_credentials() {
  local cfg count
  cfg="$("$@" config 2>/dev/null || true)"
  count="$(printf '%s\n' "${cfg}" | grep -c "CNS_REMOTE_DOCKER_SSH_KEY_PATH: ${CNS_REMOTE_DOCKER_SSH_KEY_PATH}" || true)"
  if [[ "${count}" -lt 2 ]]; then
    echo "::error::Rendered compose config missing CNS_REMOTE_DOCKER_SSH_KEY_PATH for backend and/or runner."
    printf '%s\n' "${cfg}" | grep CNS_REMOTE_DOCKER_SSH_KEY_PATH || true
    exit 1
  fi
  echo "Rendered compose config: CNS_REMOTE_DOCKER_SSH_KEY_PATH present for backend and runner"
}

verify_infra_credentials_in_containers() {
  local compose_cmd=("$@")
  verify_gcp_terraform_credentials_in_container backend "${compose_cmd[@]}"
  verify_gcp_terraform_credentials_in_container runner "${compose_cmd[@]}"
  verify_remote_docker_ssh_credentials_in_container backend "${compose_cmd[@]}"
  verify_remote_docker_ssh_credentials_in_container runner "${compose_cmd[@]}"
}
