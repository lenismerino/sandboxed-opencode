#!/bin/bash
set -Euo pipefail

readonly LOG_DIR="/home/agent/projects/logs"
readonly LOG_FILE="${LOG_DIR}/portscan.jsonl"
readonly INTERVAL="${PORTSCAN_INTERVAL:-300}"

expected_ports="${OPENCODE_PORT:-3000}|${APP_PORT:-7860}"
if [ "${OPERATION_MODE:-}" = "conductor" ]; then
  expected_ports="${expected_ports}|4096|${MCP_BRIDGE_PORT:-8443}"
fi
if [ "${DASHBOARD_ENABLED:-false}" = "true" ]; then
  expected_ports="${expected_ports}|${DASHBOARD_PORT:-8080}"
fi

expected_json_array="$(echo "$expected_ports" | jq -c -R 'split("|")')"

mkdir -p "$LOG_DIR"

while true; do
  timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

  listeners="$(ss -tlnp 2>/dev/null | tail -n +2 || true)"
  if [ -z "$listeners" ]; then
    jq -n \
      --arg ts "$timestamp" \
      --argjson ep "$expected_json_array" \
      '{timestamp: $ts, status: "ok", expected_ports: $ep, unexpected: []}' >> "$LOG_FILE"
    sleep "$INTERVAL"
    continue
  fi

  unexpected_json="[]"
  has_unexpected=false
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    port="$(echo "$line" | awk '{print $4}' | rev | cut -d: -f1 | rev)"
    if ! echo "$port" | grep -qE "^(${expected_ports})$"; then
      addr="$(echo "$line" | awk '{print $4}')"
      proc="$(echo "$line" | awk '{print $6}' | tr -d '"')"
      unexpected_json="$(echo "$unexpected_json" | jq --arg a "$addr" --arg p "$proc" '. + [{"address": $a, "process": $p}]')"
      has_unexpected=true
    fi
  done <<< "$listeners"

  if [ "$has_unexpected" = "true" ]; then
    status="warning"
  else
    status="ok"
  fi

  jq -cn \
    --arg ts "$timestamp" \
    --arg st "$status" \
    --argjson ep "$expected_json_array" \
    --argjson unexp "$unexpected_json" \
    '{timestamp: $ts, status: $st, expected_ports: $ep, unexpected: $unexp}' >> "$LOG_FILE"

  sleep "$INTERVAL"
done
