#!/bin/bash
set -Eeuo pipefail

# Configure Git
git config --global user.name "${GIT_USERNAME:-Agent Coder}"
git config --global user.email "${GIT_EMAIL:-agent@sandboxed.local}"
git config --global init.defaultBranch main
git config --global --add safe.directory /home/agent/projects

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
  BASE_URL="http://host.docker.internal:52625/v1"
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

jq -n \
  --arg schema "https://opencode.ai/config.json" \
  --arg provider_id "$PROVIDER_ID" \
  --arg provider_name "$PROVIDER_NAME" \
  --arg base_url "$BASE_URL" \
  --arg model "$ACTIVE_MODEL" \
  '{
    "$schema": $schema,
    provider: {
      ($provider_id): {
        npm: "@ai-sdk/openai-compatible",
        name: $provider_name,
        options: {baseURL: $base_url},
        models: {($model): {name: $model}}
      }
    },
    model: ($provider_id + "/" + $model)
  }' > /home/agent/.config/opencode/opencode.json

exec opencode web --hostname 0.0.0.0 --port "${OPENCODE_PORT:-3000}"
