#!/data/data/com.termux/files/usr/bin/bash
set -u

APP_DIR="${PARTS_ERP_DIR:-$HOME/parts-erp}"
LOG_DIR="$APP_DIR/data/logs"
CLOUDFLARED_BIN="${CLOUDFLARED_BIN:-$HOME/cloudflared}"
CLOUDFLARED_TOKEN_FILE="${CLOUDFLARED_TOKEN_FILE:-$HOME/cloudflared-token}"
mkdir -p "$LOG_DIR"

while [[ -x "$CLOUDFLARED_BIN" && -s "$CLOUDFLARED_TOKEN_FILE" ]]; do
  printf '%s cloudflared starting\n' "$(date -Iseconds)" >>"$LOG_DIR/cloudflared-supervisor.log"
  proot -b "$PREFIX/etc/resolv.conf:/etc/resolv.conf" env GODEBUG=netdns=go \
    "$CLOUDFLARED_BIN" tunnel --no-autoupdate --protocol http2 run \
    --token-file "$CLOUDFLARED_TOKEN_FILE" >>"$LOG_DIR/cloudflared.log" 2>&1
  status=$?
  printf '%s cloudflared exited status=%s; retrying in 5s\n' "$(date -Iseconds)" "$status" >>"$LOG_DIR/cloudflared-supervisor.log"
  sleep 5
done

printf '%s cloudflared supervisor stopped: binary or token missing\n' "$(date -Iseconds)" >>"$LOG_DIR/cloudflared-supervisor.log"
