#!/bin/bash
set -Eeuo pipefail

CONFIG_FILE="${CONFIG_FILE:-.env}"

if [ ! -f "$CONFIG_FILE" ]; then
  echo "Error: ${CONFIG_FILE} not found. Copy .env.example to .env and configure it."
  exit 1
fi

set -a
# shellcheck disable=SC1091
. "$CONFIG_FILE"
set +a

required_vars=(
  PROJECT_NAME
  PROJECTS_ROOT_PATH
  SHARED_SYSTEM_PATH
  TEMP_PATH
  LLM_SOURCE
  OPENCODE_PORT
  APP_PORT
  GIT_USERNAME
  GIT_EMAIL
  PYTHON_BASE_IMAGE
  UV_IMAGE
  NODE_VERSION
  OPENCODE_VERSION
  GH_VERSION
  OLLAMA_IMAGE_TAG
)

for var_name in "${required_vars[@]}"; do
  if [ -z "${!var_name:-}" ]; then
    echo "Error: ${var_name} must be set in .env"
    exit 1
  fi
done

for id_var in HOST_UID HOST_GID; do
  if [ -n "${!id_var:-}" ] && { ! [[ "${!id_var}" =~ ^[0-9]+$ ]] || [ "${!id_var}" -eq 0 ]; }; then
    echo "Error: ${id_var} must be a non-zero numeric ID so the agent never runs as root."
    exit 1
  fi
done

validate_port_value() {
  local port_name="$1"
  local port_value="$2"

  if ! [[ "$port_value" =~ ^[0-9]+$ ]] || [ "$port_value" -lt 1024 ] || [ "$port_value" -gt 65535 ]; then
    echo "Error: ${port_name} must be an integer from 1024 to 65535."
    exit 1
  fi

  if [ -f config/port-allowlist.txt ] && ! grep -Fxq "$port_value" config/port-allowlist.txt; then
    echo "Error: ${port_name}=${port_value} is not in config/port-allowlist.txt."
    exit 1
  fi
}

validate_port_value OPENCODE_PORT "$OPENCODE_PORT"
validate_port_value APP_PORT "$APP_PORT"
if [ -n "${LLM_PORT:-}" ]; then
  validate_port_value LLM_PORT "$LLM_PORT"
fi

case "$LLM_SOURCE" in
  lm_studio)
    : "${LM_STUDIO_MODEL:?LM_STUDIO_MODEL must be set when LLM_SOURCE=lm_studio}"
    ;;
  fastflow_amd)
    : "${FASTFLOW_MODEL:?FASTFLOW_MODEL must be set when LLM_SOURCE=fastflow_amd}"
    ;;
  ollama_docker)
    : "${OLLAMA_MODEL:?OLLAMA_MODEL must be set when LLM_SOURCE=ollama_docker}"
    ;;
  *)
    echo "Error: LLM_SOURCE must be one of: lm_studio, fastflow_amd, ollama_docker"
    exit 1
    ;;
esac

if [[ ! "$PROJECT_NAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "Error: PROJECT_NAME must be non-empty and contain only alphanumeric characters, hyphens, or underscores."
  exit 1
fi

for path_var in PROJECTS_ROOT_PATH SHARED_SYSTEM_PATH TEMP_PATH; do
  path_value="${!path_var}"
  if [ "${path_value#/}" = "$path_value" ]; then
    echo "Error: ${path_var} must be an absolute path."
    exit 1
  fi
done

if [ -n "${GITHUB_TOKEN:-}" ] && [ -n "${GH_TOKEN:-}" ] && [ "$GITHUB_TOKEN" != "$GH_TOKEN" ]; then
  echo "Error: Set only one of GITHUB_TOKEN or GH_TOKEN, or set them to the same value."
  exit 1
fi

if [ -f config/apt-package-allowlist.txt ]; then
  if grep -Ev '^(#.*|$|[a-z0-9][a-z0-9+._-]*)$' config/apt-package-allowlist.txt >/dev/null; then
    echo "Error: config/apt-package-allowlist.txt contains invalid package names."
    exit 1
  fi

  package_entries="$(grep -Ev '^(#.*|$)' config/apt-package-allowlist.txt)"
  if [ "$package_entries" != "$(printf '%s\n' "$package_entries" | sort -u)" ]; then
    echo "Error: config/apt-package-allowlist.txt must be sorted and deduplicated."
    exit 1
  fi
fi

if [ -f config/port-allowlist.txt ]; then
  if grep -Ev '^(#.*|$|[0-9]+)$' config/port-allowlist.txt >/dev/null; then
    echo "Error: config/port-allowlist.txt contains invalid port entries."
    exit 1
  fi

  port_entries="$(grep -Ev '^(#.*|$)' config/port-allowlist.txt)"
  if [ "$port_entries" != "$(printf '%s\n' "$port_entries" | sort -n -u)" ]; then
    echo "Error: config/port-allowlist.txt must be numerically sorted and deduplicated."
    exit 1
  fi
fi

echo "Configuration is valid."
