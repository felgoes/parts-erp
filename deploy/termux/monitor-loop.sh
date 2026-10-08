#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
APP_DIR="${PARTS_ERP_DIR:-$HOME/parts-erp}"
RUN_DIR="$APP_DIR/data/run"
LOG_DIR="$APP_DIR/data/logs"
VENV="$APP_DIR/backend/.venv-termux"
CLOUDFLARED_BIN="${CLOUDFLARED_BIN:-$HOME/cloudflared}"
CLOUDFLARED_TOKEN_FILE="${CLOUDFLARED_TOKEN_FILE:-$HOME/cloudflared-token}"
mkdir -p "$RUN_DIR" "$LOG_DIR"

ensure_cloudflared() {
  [[ -x "$CLOUDFLARED_BIN" && -s "$CLOUDFLARED_TOKEN_FILE" ]] || return 0
  local pid_file="$RUN_DIR/cloudflared.pid"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    return 0
  fi
  rm -f "$pid_file"
  nohup "$APP_DIR/deploy/termux/cloudflared-supervisor.sh" \
    >>"$LOG_DIR/cloudflared-supervisor.log" 2>&1 </dev/null &
  echo $! >"$pid_file"
  printf '%s cloudflared supervisor relaunched by monitor\n' "$(date -Iseconds)" >>"$LOG_DIR/cloudflared-supervisor.log"
}

ensure_core_services() {
  # start.sh is idempotent and restarts components whose PID disappeared.
  PARTS_ERP_WATCHDOG=1 PARTS_ERP_DIR="$APP_DIR" "$APP_DIR/deploy/termux/start.sh" \
    >>"$LOG_DIR/watchdog-start.log" 2>&1 || true
}

while true; do
  if [[ -f "$RUN_DIR/maintenance" ]]; then sleep 30; continue; fi
  ensure_core_services
  (cd "$APP_DIR/backend" && timeout 45 "$VENV/bin/python" -m app.monitor) >>"$LOG_DIR/monitor.log" 2>&1 || true
  sleep 60
done
