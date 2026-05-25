#!/bin/bash
set -Eeuo pipefail

CONFIG_FILE="${CONFIG_FILE:-.env}"

# Load environment variables
if [ -f "$CONFIG_FILE" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$CONFIG_FILE"
  set +a
else
  echo "Error: ${CONFIG_FILE} not found. Copy .env.example to .env and configure it first."
  exit 1
fi

: "${PROJECT_NAME:?PROJECT_NAME must be set in .env}"
: "${PROJECTS_ROOT_PATH:?PROJECTS_ROOT_PATH must be set in .env}"

PROJECT_DIR="${PROJECTS_ROOT_PATH}/${PROJECT_NAME}"

# Ensure the master AGENTS.md exists in the root directory
if [ ! -f "AGENTS.md" ]; then
  echo "Error: AGENTS.md not found in the root repository. Please ensure it exists."
  exit 1
fi

echo "Ensuring project workspace exists for: ${PROJECT_NAME}..."

# Always ensure target directories exist
PKG_NAME="${PROJECT_NAME//-/_}"
mkdir -p "$PROJECT_DIR/docs" "$PROJECT_DIR/artifacts" "$PROJECT_DIR/logs" "$PROJECT_DIR/skills" "$PROJECT_DIR/src/$PKG_NAME"

# Drop an __init__.py so the agent immediately recognizes it as the active package
touch "$PROJECT_DIR/src/$PKG_NAME/__init__.py"

# --- Dynamic LLM Routing Injection (Always Runs) ---
if [ "$LLM_SOURCE" = "lm_studio" ]; then
  INJECT_URL="http://host.docker.internal:${LLM_PORT:-1234}/v1"
  INJECT_MODEL="$LM_STUDIO_MODEL"
elif [ "$LLM_SOURCE" = "fastflow_amd" ]; then
  INJECT_URL="http://host.docker.internal:52625/v1"
  INJECT_MODEL="$FASTFLOW_MODEL"
elif [ "$LLM_SOURCE" = "ollama_docker" ]; then
  INJECT_URL="http://opencode-llm:11434/v1"
  INJECT_MODEL="$OLLAMA_MODEL"
else
  echo "Error: Invalid LLM_SOURCE '${LLM_SOURCE:-}' in .env"
  exit 1
fi

cat <<EOF > "$PROJECT_DIR/.env"
# Dynamic Configuration injected by xl-sandboxed-opencode
LLM_BASE_URL="${INJECT_URL}"
LLM_MODEL_NAME="${INJECT_MODEL}"
APP_PORT="${APP_PORT:-7860}"
EOF
# ------------------------------------------

# Generate the internal Python Makefile for the agent in a temporary location.
TEMPLATE_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMPLATE_DIR"' EXIT
cat > "$TEMPLATE_DIR/Makefile" << EOF
.PHONY: setup format lint typecheck test run
setup:
	uv venv && uv sync
format:
	uv run ruff format . && uv run ruff check --fix .
lint:
	uv run ruff check .
typecheck:
	uv run mypy --strict .
test:
	uv run pytest -v
run:
	uv run python -m ${PKG_NAME}
EOF

# Always inject the latest constraints and commands into the project
cp AGENTS.md "$PROJECT_DIR/"
cp "$TEMPLATE_DIR/Makefile" "$PROJECT_DIR/"
if [ -d "skills" ]; then
  cp -R skills/. "$PROJECT_DIR/skills/"
fi

# Only initialize Git and write README if it's a completely new project
if [ ! -d "$PROJECT_DIR/.git" ]; then
  echo "# ${PROJECT_NAME}" > "$PROJECT_DIR/README.md"
  echo "Project initialized via xl-sandboxed-opencode." >> "$PROJECT_DIR/README.md"

  cd "$PROJECT_DIR"
  git init
  git config user.name "${GIT_USERNAME:-Agent Coder}"
  git config user.email "${GIT_EMAIL:-agent@sandboxed.local}"
  git add .
  git commit -m "chore: initialize project with strict agent templates"
  echo "Project '$PROJECT_NAME' created securely."
else
  echo "Existing project '$PROJECT_NAME' updated with latest templates and .env."
fi
