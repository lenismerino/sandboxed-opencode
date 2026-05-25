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
if [ -n "${DASHBOARD_PORT:-}" ]; then
  validate_port_value DASHBOARD_PORT "$DASHBOARD_PORT"
fi
if [ -n "${MCP_BRIDGE_PORT:-}" ]; then
  validate_port_value MCP_BRIDGE_PORT "$MCP_BRIDGE_PORT"
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

# --- Security hardening variable validation ---

for bool_var in PORTSCAN_ENABLED RESOURCE_MONITOR_ENABLED AUTOLOG_ENABLED SECRET_SCAN_STRICT DASHBOARD_ENABLED; do
  if [ -n "${!bool_var:-}" ] && [[ "${!bool_var}" != "true" && "${!bool_var}" != "false" ]]; then
    echo "Error: ${bool_var} must be 'true' or 'false'."
    exit 1
  fi
done

if [ -n "${NETWORK_EGRESS:-}" ] && [[ "$NETWORK_EGRESS" != "restricted" && "$NETWORK_EGRESS" != "full" ]]; then
  echo "Error: NETWORK_EGRESS must be 'restricted' or 'full'."
  exit 1
fi

for int_var in ULIMIT_NOFILE ULIMIT_NPROC PORTSCAN_INTERVAL RESOURCE_MONITOR_INTERVAL DASHBOARD_REFRESH_INTERVAL; do
  if [ -n "${!int_var:-}" ] && ! [[ "${!int_var}" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: ${int_var} must be a positive integer."
    exit 1
  fi
done

if [ -n "${SECCOMP_PROFILE:-}" ] && [ "$SECCOMP_PROFILE" != "unconfined" ] && [ ! -f "$SECCOMP_PROFILE" ]; then
  echo "Error: SECCOMP_PROFILE file '${SECCOMP_PROFILE}' does not exist."
  exit 1
fi

# --- Interface & operation mode validation ---

if [ -n "${OPENCODE_INTERFACE:-}" ] && [[ "$OPENCODE_INTERFACE" != "web" && "$OPENCODE_INTERFACE" != "tui" ]]; then
  echo "Error: OPENCODE_INTERFACE must be 'web' or 'tui'."
  exit 1
fi

if [ -n "${OPERATION_MODE:-}" ] && [[ "$OPERATION_MODE" != "interactive" && "$OPERATION_MODE" != "autonomous" && "$OPERATION_MODE" != "conductor" ]]; then
  echo "Error: OPERATION_MODE must be 'interactive', 'autonomous', or 'conductor'."
  exit 1
fi

if [ "${OPERATION_MODE:-interactive}" = "autonomous" ] && [ -z "${TASK_FILE:-}" ]; then
  echo "Error: TASK_FILE must be set when OPERATION_MODE=autonomous."
  exit 1
fi

# --- Provider-specific validation ---

if [ -n "${OLLAMA_NUM_GPU:-}" ] && ! [[ "${OLLAMA_NUM_GPU}" =~ ^[0-9]+$ ]]; then
  echo "Error: OLLAMA_NUM_GPU must be a non-negative integer."
  exit 1
fi

# --- MCP validation ---

if [ -n "${MCP_CONFIG_FILE:-}" ] && [ ! -f "$MCP_CONFIG_FILE" ]; then
  if [ ! -f "${PROJECTS_ROOT_PATH}/${PROJECT_NAME}/${MCP_CONFIG_FILE}" ] && \
     [ ! -f "${SHARED_SYSTEM_PATH}/${MCP_CONFIG_FILE}" ]; then
    echo "Warning: MCP_CONFIG_FILE '${MCP_CONFIG_FILE}' not found in repo, project, or shared paths."
  fi
fi

if [ -f "$CONFIG_FILE" ]; then
  env_perms=$(stat -c '%a' "$CONFIG_FILE" 2>/dev/null || stat -f '%Lp' "$CONFIG_FILE" 2>/dev/null || true)
  if [ -n "$env_perms" ] && [ "$env_perms" != "600" ] && [ "$env_perms" != "400" ] && [ "$env_perms" != "640" ]; then
    echo "Warning: ${CONFIG_FILE} has permissions ${env_perms}; consider restricting to 600."
  fi
fi

echo "Configuration is valid."
