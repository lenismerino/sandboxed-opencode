#!/bin/bash
set -Eeuo pipefail

CONFIG_FILE="${CONFIG_FILE:-.env.example}" ./scripts/validate_config.sh

for script_path in \
  entrypoint.sh \
  new_project.sh \
  scripts/agent-apt-install \
  scripts/agent-kill-port \
  scripts/security_check.sh \
  scripts/validate_config.sh \
  scripts/monitor-ports.sh \
  scripts/monitor-resources.sh \
  scripts/monitor-logs.sh \
  scripts/dashboard-server.sh; do
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

if ! grep -Fq 'read_only: true' docker-compose.yml; then
  echo "Error: compose workspace must use read_only: true." >&2
  exit 1
fi

if ! grep -Fq 'seccomp=' docker-compose.yml; then
  echo "Error: compose workspace must reference a seccomp profile." >&2
  exit 1
fi

# Core secret patterns (always active)
if grep -RIn --exclude-dir=.git --exclude='*.md' --exclude='.env' --exclude='.env.example' \
  -E '(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})' .; then
  echo "Error: potential committed secret detected." >&2
  exit 1
fi

# Load config for SECRET_SCAN_STRICT toggle
if [ -f "${CONFIG_FILE:-.env.example}" ]; then
  set -a
  # shellcheck disable=SC1090
  . "${CONFIG_FILE:-.env.example}"
  set +a
fi

# Python syntax compilation check
for py_file in \
  scripts/dashboard.py \
  scripts/mcp-bridge.py \
  scripts/crystallize_skill.py \
  scripts/model_profile.py \
  scripts/skills_manager.py \
  scripts/run_harness.py; do
  python3 -m py_compile "$py_file"
done

# Check harness, tools, plugins
python3 -m unittest discover -s harness -p "*_test.py" >/dev/null

if [ "${SECRET_SCAN_STRICT:-true}" = "true" ]; then
  if grep -RIn --exclude-dir=.git --exclude='*.md' --exclude='.env' --exclude='.env.example' \
    -E 'AKIA[0-9A-Z]{16}' .; then
    echo "Error: potential AWS access key detected." >&2
    exit 1
  fi

  if grep -RIn --exclude-dir=.git --exclude='*.md' --exclude='.env' --exclude='.env.example' \
    --exclude='security_check.sh' -e '-----BEGIN .*PRIVATE KEY-----' .; then
    echo "Error: potential private key detected." >&2
    exit 1
  fi

  if grep -RIn --exclude-dir=.git --exclude='*.md' --exclude='.env' --exclude='.env.example' \
    -E 'eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.' .; then
    echo "Error: potential JWT token detected." >&2
    exit 1
  fi

  if grep -RIn --exclude-dir=.git --exclude='*.md' --exclude='.env' --exclude='.env.example' \
    -E 'xox[bpors]-[A-Za-z0-9-]{10,}' .; then
    echo "Error: potential Slack token detected." >&2
    exit 1
  fi

  if grep -RIn --exclude-dir=.git --exclude='*.md' --exclude='.env' --exclude='.env.example' \
    --exclude='security_check.sh' -E '(hf_[A-Za-z0-9]{34,}|sk-ant-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{35})' .; then
    echo "Error: potential AI provider token detected." >&2
    exit 1
  fi
fi

echo "Security checks passed."
