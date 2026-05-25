#!/bin/bash
set -Eeuo pipefail

CONFIG_FILE="${CONFIG_FILE:-.env.example}" ./scripts/validate_config.sh

for script_path in \
  entrypoint.sh \
  new_project.sh \
  scripts/agent-apt-install \
  scripts/agent-kill-port \
  scripts/security_check.sh \
  scripts/validate_config.sh; do
  bash -n "$script_path"
done

docker compose --env-file "${CONFIG_FILE:-.env.example}" config >/dev/null

if ! grep -Eq '^USER agent$' Dockerfile; then
  echo "Error: Dockerfile must end runtime stages as USER agent." >&2
  exit 1
fi

if grep -RIn 'apt-get install \*' Dockerfile scripts docker-compose.yml AGENTS.md README.md; then
  echo "Error: broad apt-get sudo/install pattern detected." >&2
  exit 1
fi

if ! grep -Fq '127.0.0.1:' docker-compose.yml; then
  echo "Error: compose ports must bind to 127.0.0.1." >&2
  exit 1
fi

if grep -RIn --exclude-dir=.git --exclude='*.md' --exclude='.env' --exclude='.env.example' \
  -E '(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})' .; then
  echo "Error: potential committed secret detected." >&2
  exit 1
fi

echo "Security checks passed."
