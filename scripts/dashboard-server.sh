#!/bin/bash
set -Euo pipefail

readonly LOG_DIR="/home/agent/projects/logs"
readonly PUBLIC_DIR="${DASHBOARD_PUBLIC_DIR:-/tmp/dashboard-public}"
readonly PORT="${DASHBOARD_PORT:-8080}"
readonly REFRESH="${DASHBOARD_REFRESH_INTERVAL:-30}"

mkdir -p "$LOG_DIR" "$PUBLIC_DIR"

python3 /home/agent/app/dashboard.py

cd "$PUBLIC_DIR"
python3 -m http.server "$PORT" --bind 0.0.0.0 &
server_pid=$!
echo "Dashboard server started on port ${PORT} (PID ${server_pid})"

while true; do
  sleep "$REFRESH"
  python3 /home/agent/app/dashboard.py
done
