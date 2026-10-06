#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APP_DIR="${PARTS_ERP_DIR:-$HOME/parts-erp}"
RUN_DIR="$APP_DIR/data/run"
LOG_DIR="$APP_DIR/data/logs"
VENV="$APP_DIR/backend/.venv-termux"
export PYTHONPATH="$APP_DIR/backend${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p "$RUN_DIR" "$LOG_DIR" "$APP_DIR/data/redis" "$APP_DIR/data/documents"

is_running() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

if ! is_running "$RUN_DIR/redis.pid"; then
  rm -f "$RUN_DIR/redis.pid"
  redis-server "$APP_DIR/deploy/termux/redis.conf"
fi

if ! is_running "$RUN_DIR/api.pid"; then
  rm -f "$RUN_DIR/api.pid"
  (
    cd "$APP_DIR/backend"
    exec nohup "$VENV/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
  ) >>"$LOG_DIR/api.log" 2>&1 &
  echo $! >"$RUN_DIR/api.pid"
fi

if ! is_running "$RUN_DIR/worker.pid"; then
  rm -f "$RUN_DIR/worker.pid"
  (
    cd "$APP_DIR/backend"
    exec nohup "$VENV/bin/python" -m arq app.workers.settings.WorkerSettings
  ) >>"$LOG_DIR/worker.log" 2>&1 &
  echo $! >"$RUN_DIR/worker.pid"
fi

if ! is_running "$RUN_DIR/monitor.pid"; then
  rm -f "$RUN_DIR/monitor.pid"
  nohup "$APP_DIR/deploy/termux/monitor-loop.sh" >>"$LOG_DIR/monitor-loop.log" 2>&1 </dev/null &
  echo $! >"$RUN_DIR/monitor.pid"
fi

if ! is_running "$RUN_DIR/nginx.pid"; then
  rm -f "$RUN_DIR/nginx.pid"
  nginx -c "$APP_DIR/deploy/termux/nginx.conf"
fi

# Android does not expose /etc/resolv.conf to Termux. cloudflared is a Go
# binary and otherwise falls back to an unavailable ::1 resolver after a
# reboot, producing Cloudflare 1033. Bind the Termux resolver into a small
# proot namespace and keep the tunnel alongside the ERP services.
CLOUDFLARED_BIN="${CLOUDFLARED_BIN:-$HOME/cloudflared}"
CLOUDFLARED_TOKEN_FILE="${CLOUDFLARED_TOKEN_FILE:-$HOME/cloudflared-token}"
if [[ -x "$CLOUDFLARED_BIN" && -s "$CLOUDFLARED_TOKEN_FILE" ]] \
  && ! is_running "$RUN_DIR/cloudflared.pid"; then
  rm -f "$RUN_DIR/cloudflared.pid"
  nohup proot -b "$PREFIX/etc/resolv.conf:/etc/resolv.conf" env GODEBUG=netdns=go \
    "$CLOUDFLARED_BIN" tunnel --no-autoupdate --protocol http2 run \
    --token-file "$CLOUDFLARED_TOKEN_FILE" >>"$LOG_DIR/cloudflared.log" 2>&1 </dev/null &
  echo $! >"$RUN_DIR/cloudflared.pid"
fi

for _attempt in {1..20}; do
  if curl --fail --silent http://127.0.0.1:8000/health >/dev/null; then
    printf 'Parts ERP iniciado em http://127.0.0.1:8080\n'
    exit 0
  fi
  sleep 1
done

echo "A API não respondeu dentro de 20 segundos. Consulte data/logs/api.log." >&2
exit 1
