#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APP_DIR="${PARTS_ERP_DIR:-$HOME/parts-erp}"
RUN_DIR="$APP_DIR/data/run"
mkdir -p "$RUN_DIR"
exec 9>"$RUN_DIR/start.lock"
flock -w 95 9 || exit 1
touch "$RUN_DIR/maintenance"

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
    if kill -0 "$pid" 2>/dev/null; then
      kill -KILL "$pid" 2>/dev/null || true
    fi
    rm -f "$pid_file"
  fi
}

stop_all_cloudflared() {
  for pid in $(ps -ef | awk '$0 ~ /cloudflared tunnel/ {print $2}'); do
    kill "$pid" 2>/dev/null || true
  done
}

stop_pid monitor
stop_pid nginx
# Deploys keep the connector attached to Cloudflare while the origin is updated.
# This may cause a brief origin 502, but prevents Error 1033 from losing the last connector.
if [[ "${PARTS_ERP_PRESERVE_CLOUDFLARED:-0}" == 1 ]]; then
  printf 'Cloudflared preservado durante o deploy.\n'
else
  stop_pid cloudflared
  stop_all_cloudflared
fi
stop_pid worker
stop_pid api
stop_pid redis
printf 'Parts ERP parado.\n'
