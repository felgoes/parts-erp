#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APP_DIR="${PARTS_ERP_DIR:-$HOME/parts-erp}"
RUN_DIR="$APP_DIR/data/run"

stop_pid() {
  local name="$1"
  local pid_file="$RUN_DIR/$name.pid"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file")"
    kill "$pid" 2>/dev/null || true
    for _attempt in {1..10}; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.2
    done
    rm -f "$pid_file"
  fi
}

stop_pid nginx
stop_pid monitor
stop_pid worker
stop_pid api
stop_pid redis
printf 'Parts ERP parado.\n'
