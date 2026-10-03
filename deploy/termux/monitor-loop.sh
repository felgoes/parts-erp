#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
APP_DIR="${PARTS_ERP_DIR:-$HOME/parts-erp}"
RUN_DIR="$APP_DIR/data/run"
LOG_DIR="$APP_DIR/data/logs"
VENV="$APP_DIR/backend/.venv-termux"
mkdir -p "$RUN_DIR" "$LOG_DIR"
while true; do
  (cd "$APP_DIR/backend" && "$VENV/bin/python" -m app.monitor) >>"$LOG_DIR/monitor.log" 2>&1 || true
  sleep 60
done
