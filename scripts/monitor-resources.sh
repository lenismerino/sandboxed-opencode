#!/bin/bash
set -Euo pipefail

readonly LOG_DIR="/home/agent/projects/logs"
readonly LOG_FILE="${LOG_DIR}/resources.jsonl"
readonly INTERVAL="${RESOURCE_MONITOR_INTERVAL:-60}"

mkdir -p "$LOG_DIR"

while true; do
  timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

  mem_total=0
  mem_available=0
  swap_total=0
  swap_free=0
  if [ -f /proc/meminfo ]; then
    mem_total="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
    mem_available="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
    swap_total="$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)"
    swap_free="$(awk '/^SwapFree:/ {print $2}' /proc/meminfo)"
  fi

  [[ ! "$mem_total" =~ ^[0-9]+$ ]] && mem_total=0
  [[ ! "$mem_available" =~ ^[0-9]+$ ]] && mem_available=0
  [[ ! "$swap_total" =~ ^[0-9]+$ ]] && swap_total=0
  [[ ! "$swap_free" =~ ^[0-9]+$ ]] && swap_free=0

  if [ "$mem_total" -gt 0 ] 2>/dev/null; then
    mem_used_pct="$(awk "BEGIN {printf \"%.1f\", (($mem_total - $mem_available) / $mem_total) * 100}")"
  else
    mem_used_pct="0.0"
  fi

  proc_count="$(ps aux 2>/dev/null | tail -n +2 | wc -l)"

  top_procs="[]"
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    user="$(echo "$line" | awk '{print $1}')"
    pid="$(echo "$line" | awk '{print $2}')"
    cpu="$(echo "$line" | awk '{print $3}')"
    mem="$(echo "$line" | awk '{print $4}')"
    cmd="$(echo "$line" | awk '{for(i=11;i<=NF;i++) printf "%s ", $i; print ""}'| sed 's/ $//')"
    
    if [[ "$pid" =~ ^[0-9]+$ ]]; then
      top_procs="$(echo "$top_procs" | jq \
        --arg u "$user" --arg p "$pid" --arg c "$cpu" --arg m "$mem" --arg cm "$cmd" \
        '. + [{"user":$u,"pid":($p|tonumber),"cpu":($c|tonumber),"mem":($m|tonumber),"command":$cm}]')"
    fi
  done <<< "$(ps aux --sort=-%mem 2>/dev/null | tail -n +2 | head -10)"

  jq -cn \
    --arg ts "$timestamp" \
    --argjson mt "$mem_total" \
    --argjson ma "$mem_available" \
    --arg mu "$mem_used_pct" \
    --argjson st "$swap_total" \
    --argjson sf "$swap_free" \
    --argjson pc "$proc_count" \
    --argjson tp "$top_procs" \
    '{timestamp:$ts, mem_total_kb:$mt, mem_available_kb:$ma, mem_used_pct:($mu|tonumber), swap_total_kb:$st, swap_free_kb:$sf, process_count:$pc, top_processes:$tp}' >> "$LOG_FILE"

  sleep "$INTERVAL"
done
