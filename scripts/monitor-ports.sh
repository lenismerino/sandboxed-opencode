#!/bin/bash
set -Euo pipefail

readonly LOG_DIR="/home/agent/projects/logs"
readonly LOG_FILE="${LOG_DIR}/portscan.jsonl"
readonly INTERVAL="${PORTSCAN_INTERVAL:-300}"

expected_ports="${OPENCODE_PORT:-3000}|${APP_PORT:-7860}"

mkdir -p "$LOG_DIR"

while true; do
  timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

  listeners="$(ss -tlnp 2>/dev/null | tail -n +2 || true)"
  if [ -z "$listeners" ]; then
    printf '{"timestamp":"%s","status":"ok","expected_ports":["%s","%s"],"unexpected":[]}\n' \
      "$timestamp" "${OPENCODE_PORT:-3000}" "${APP_PORT:-7860}" >> "$LOG_FILE"
    sleep "$INTERVAL"
    continue
  fi

  unexpected_json="[]"
  has_unexpected=false
  while IFS= read -r line; do
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
    --arg ep1 "${OPENCODE_PORT:-3000}" \
    --arg ep2 "${APP_PORT:-7860}" \
    --argjson unexp "$unexpected_json" \
    '{timestamp: $ts, status: $st, expected_ports: [$ep1, $ep2], unexpected: $unexp}' >> "$LOG_FILE"

  sleep "$INTERVAL"
done
