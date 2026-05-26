#!/bin/bash
set -Eeuo pipefail

# Configure Git (write to tmpfs since root filesystem is read-only)
export GIT_CONFIG_GLOBAL="/tmp/gitconfig"
export XDG_CONFIG_HOME="/home/agent/.config"
mkdir -p /home/agent/.config/git
git config --global user.name "${GIT_USERNAME:-Agent Coder}"
git config --global user.email "${GIT_EMAIL:-agent@sandboxed.local}"
git config --global init.defaultBranch main
git config --global --add safe.directory /home/agent/projects

# Signal handling for graceful shutdown of monitoring processes
cleanup() {
  for pid_file in /tmp/monitor-*.pid; do
    [ -f "$pid_file" ] && kill "$(cat "$pid_file")" 2>/dev/null || true
  done
}
trap cleanup SIGTERM SIGINT

if [ -n "${GITHUB_TOKEN:-}" ] && [ -z "${GH_TOKEN:-}" ]; then
  export GH_TOKEN="$GITHUB_TOKEN"
fi

if [ -n "${GH_TOKEN:-}" ]; then
  gh auth setup-git --hostname github.com >/dev/null 2>&1 || \
    echo "Warning: GitHub token was provided, but gh auth setup-git did not complete."
fi

mkdir -p /home/agent/temp/uv_cache /home/agent/temp/ruff_cache /home/agent/temp/mypy_cache /home/agent/temp/pytest_cache
mkdir -p /home/agent/.config/opencode

# Route the LLM Connection
if [ "$LLM_SOURCE" = "lm_studio" ]; then
  : "${LM_STUDIO_MODEL:?LM_STUDIO_MODEL must be set when LLM_SOURCE=lm_studio}"
  PROVIDER_ID="lmstudio"
  PROVIDER_NAME="LM Studio (Host)"
  BASE_URL="http://host.docker.internal:${LLM_PORT:-1234}/v1"
  ACTIVE_MODEL="$LM_STUDIO_MODEL"
elif [ "$LLM_SOURCE" = "fastflow_amd" ]; then
  : "${FASTFLOW_MODEL:?FASTFLOW_MODEL must be set when LLM_SOURCE=fastflow_amd}"
  PROVIDER_ID="fastflow"
  PROVIDER_NAME="FastFlowLM (Host NPU)"
  BASE_URL="http://host.docker.internal:${LLM_PORT:-52625}/v1"
  ACTIVE_MODEL="$FASTFLOW_MODEL"
elif [ "$LLM_SOURCE" = "ollama_docker" ]; then
  : "${OLLAMA_MODEL:?OLLAMA_MODEL must be set when LLM_SOURCE=ollama_docker}"
  PROVIDER_ID="ollama"
  PROVIDER_NAME="Ollama (Isolated)"
  BASE_URL="http://opencode-llm:11434/v1"
  ACTIVE_MODEL="$OLLAMA_MODEL"
else
  echo "Error: Invalid LLM_SOURCE defined in .env"
  exit 1
fi

API_KEY="${LM_STUDIO_API_KEY:-}"

jq -n \
  --arg schema "https://opencode.ai/config.json" \
  --arg provider_id "$PROVIDER_ID" \
  --arg provider_name "$PROVIDER_NAME" \
  --arg base_url "$BASE_URL" \
  --arg model "$ACTIVE_MODEL" \
  --arg api_key "$API_KEY" \
  '{
    "$schema": $schema,
    provider: {
      ($provider_id): {
        npm: "@ai-sdk/openai-compatible",
        name: $provider_name,
        options: ({baseURL: $base_url} + (if $api_key != "" then {apiKey: $api_key} else {} end)),
        models: {($model): {name: $model}}
      }
    },
    model: ($provider_id + "/" + $model)
  }' > /home/agent/.config/opencode/opencode.json

# Merge MCP server configuration if provided
if [ -n "${MCP_CONFIG_FILE:-}" ]; then
  mcp_path="${MCP_CONFIG_FILE}"
  if [ ! -f "$mcp_path" ] && [ -f "/home/agent/projects/${mcp_path}" ]; then
    mcp_path="/home/agent/projects/${mcp_path}"
  elif [ ! -f "$mcp_path" ] && [ -f "/home/agent/shared/${mcp_path}" ]; then
    mcp_path="/home/agent/shared/${mcp_path}"
  fi

  if [ -f "$mcp_path" ]; then
    if jq --slurpfile mcp "$mcp_path" '.mcp = $mcp[0]' \
      /home/agent/.config/opencode/opencode.json > /tmp/opencode-merged.json 2>/dev/null; then
      mv /tmp/opencode-merged.json /home/agent/.config/opencode/opencode.json
      echo "MCP configuration loaded from ${mcp_path}"
    else
      echo "Warning: MCP_CONFIG_FILE '${mcp_path}' contains invalid JSON or could not be merged."
    fi
  else
    echo "Warning: MCP_CONFIG_FILE '${MCP_CONFIG_FILE}' not found."
  fi
fi

# Start optional monitoring and dashboard (not compatible with TUI — TUI uses exec)
if [ "${OPENCODE_INTERFACE:-web}" != "tui" ]; then
  if [ "${PORTSCAN_ENABLED:-false}" = "true" ]; then
    /home/agent/app/monitor-ports.sh &
    echo $! > /tmp/monitor-ports.pid
  fi

  if [ "${RESOURCE_MONITOR_ENABLED:-false}" = "true" ]; then
    /home/agent/app/monitor-resources.sh &
    echo $! > /tmp/monitor-resources.pid
  fi

  if [ "${AUTOLOG_ENABLED:-false}" = "true" ]; then
    /home/agent/app/monitor-logs.sh &
    echo $! > /tmp/monitor-logs.pid
  fi

  if [ "${DASHBOARD_ENABLED:-false}" = "true" ]; then
    /home/agent/app/dashboard-server.sh &
    echo $! > /tmp/monitor-dashboard.pid
  fi
fi

# Launch based on operation mode
if [ "${OPERATION_MODE:-interactive}" = "autonomous" ]; then
  : "${TASK_FILE:?TASK_FILE must be set when OPERATION_MODE=autonomous}"
  task_path="/home/agent/projects/${TASK_FILE}"
  if [ ! -f "$task_path" ]; then
    echo "Error: Task file not found: ${task_path}"
    exit 1
  fi

  mkdir -p /home/agent/projects/logs
  echo "Autonomous mode: executing task from ${TASK_FILE}..."

  opencode run \
    --dangerously-skip-permissions \
    --file "$task_path" \
    -q \
    "You are operating in AUTONOMOUS mode. Read the attached project requirements document carefully. Follow the Software Development Cycle defined in AGENTS.md. Execute all phases end-to-end without stopping. Iterate until the project is 100% complete and the final report is generated." \
    > /home/agent/projects/logs/autonomous.log 2>&1
  exit_code=$?

  echo "Autonomous execution finished with exit code ${exit_code}."
  cleanup
  exit "$exit_code"

elif [ "${OPERATION_MODE:-interactive}" = "conductor" ]; then
  # Conductor mode: headless OpenCode + MCP bridge for external orchestration
  opencode serve --hostname 127.0.0.1 --port 4096 &
  opencode_pid=$!
  echo $opencode_pid > /tmp/monitor-opencode.pid

  echo "Waiting for OpenCode serve to become ready..."
  for i in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:4096/global/health >/dev/null 2>&1; then
      echo "OpenCode serve is ready."
      break
    fi
    if [ "$i" -eq 30 ]; then
      echo "Error: OpenCode serve did not start within 30 seconds."
      cleanup
      exit 1
    fi
    sleep 1
  done

  python3 /home/agent/app/mcp-bridge.py &
  bridge_pid=$!
  echo $bridge_pid > /tmp/monitor-bridge.pid

  echo "Conductor mode ready. MCP bridge on port ${MCP_BRIDGE_PORT:-8443}."
  echo "Connect your AI coding agent to: http://localhost:${MCP_BRIDGE_PORT:-8443}/mcp"
  wait $opencode_pid
  exit_code=$?
  cleanup
  exit "$exit_code"

else
  # Interactive mode: web UI or terminal TUI
  if [ "${OPENCODE_INTERFACE:-web}" = "tui" ]; then
    exec opencode
  else
    opencode web --hostname 0.0.0.0 --port "${OPENCODE_PORT:-3000}" &
    child=$!
    wait "$child"
    exit_code=$?
    cleanup
    exit "$exit_code"
  fi
fi
