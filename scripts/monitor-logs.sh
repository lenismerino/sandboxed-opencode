#!/bin/bash
set -Euo pipefail

readonly LOG_DIR="/home/agent/projects/logs"
readonly LOG_FILE="${LOG_DIR}/security_summary.jsonl"
readonly REPORT_INTERVAL=3600

mkdir -p "$LOG_DIR"

while true; do
  sleep "$REPORT_INTERVAL"

  timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

  proc_count="$(ps aux 2>/dev/null | tail -n +2 | wc -l)"

  mem_total=0
  mem_available=0
  if [ -f /proc/meminfo ]; then
    mem_total="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
    mem_available="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
  fi

  portscan_warnings=0
  resource_snapshots=0
  if [ -f "${LOG_DIR}/portscan.jsonl" ]; then
    portscan_warnings="$(grep -c '"status":"warning"' "${LOG_DIR}/portscan.jsonl" 2>/dev/null || echo 0)"
  fi
  if [ -f "${LOG_DIR}/resources.jsonl" ]; then
    resource_snapshots="$(wc -l < "${LOG_DIR}/resources.jsonl" 2>/dev/null || echo 0)"
  fi

  listeners_json="[]"
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    addr="$(echo "$line" | awk '{print $4}')"
    listeners_json="$(echo "$listeners_json" | jq --arg a "$addr" '. + [$a]')"
  done <<< "$(ss -tlnp 2>/dev/null | tail -n +2 || true)"

  jq -cn \
    --arg ts "$timestamp" \
    --argjson pc "$proc_count" \
    --argjson mt "$mem_total" \
    --argjson ma "$mem_available" \
    --argjson pw "$portscan_warnings" \
    --argjson rs "$resource_snapshots" \
    --argjson ls "$listeners_json" \
    '{timestamp:$ts, process_count:$pc, mem_total_kb:$mt, mem_available_kb:$ma, portscan_warnings:$pw, resource_snapshots:$rs, listeners:$ls}' >> "$LOG_FILE"
done
