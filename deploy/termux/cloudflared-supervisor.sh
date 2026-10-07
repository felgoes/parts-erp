#!/data/data/com.termux/files/usr/bin/bash
set -u

APP_DIR="${PARTS_ERP_DIR:-$HOME/parts-erp}"
LOG_DIR="$APP_DIR/data/logs"
CLOUDFLARED_BIN="${CLOUDFLARED_BIN:-$HOME/cloudflared}"
CLOUDFLARED_TOKEN_FILE="${CLOUDFLARED_TOKEN_FILE:-$HOME/cloudflared-token}"
CLOUDFLARED_ORIGIN_URL="${CLOUDFLARED_ORIGIN_URL:-http://127.0.0.1:8080}"
mkdir -p "$LOG_DIR"

backoff=5
while [[ -x "$CLOUDFLARED_BIN" && -s "$CLOUDFLARED_TOKEN_FILE" ]]; do
  if ! curl --fail --silent --max-time 5 "$CLOUDFLARED_ORIGIN_URL/health" >/dev/null; then
    printf '%s origin unavailable at %s; retrying in %ss\n' "$(date -Iseconds)" "$CLOUDFLARED_ORIGIN_URL" "$backoff" >>"$LOG_DIR/cloudflared-supervisor.log"
    sleep "$backoff"
    backoff=$((backoff < 60 ? backoff + 5 : 60))
    continue
  fi
  printf '%s cloudflared starting origin=%s\n' "$(date -Iseconds)" "$CLOUDFLARED_ORIGIN_URL" >>"$LOG_DIR/cloudflared-supervisor.log"
  proot -b "$PREFIX/etc/resolv.conf:/etc/resolv.conf" env GODEBUG=netdns=go \
    "$CLOUDFLARED_BIN" tunnel --no-autoupdate --protocol http2 run \
    --token-file "$CLOUDFLARED_TOKEN_FILE" --url "$CLOUDFLARED_ORIGIN_URL" >>"$LOG_DIR/cloudflared.log" 2>&1
  status=$?
  printf '%s cloudflared exited status=%s; retrying in %ss\n' "$(date -Iseconds)" "$status" "$backoff" >>"$LOG_DIR/cloudflared-supervisor.log"
  sleep "$backoff"
  backoff=$((backoff < 60 ? backoff + 5 : 60))
done

printf '%s cloudflared supervisor stopped: binary or token missing\n' "$(date -Iseconds)" >>"$LOG_DIR/cloudflared-supervisor.log"
