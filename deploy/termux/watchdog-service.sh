#!/data/data/com.termux/files/usr/bin/bash
set -eu
export PREFIX=/data/data/com.termux/files/usr
export PATH="$PREFIX/bin:$PATH"
export PARTS_ERP_DIR=/data/data/com.termux/files/home/parts-erp
mkdir -p "$PARTS_ERP_DIR/data/run"
exec 8>"$PARTS_ERP_DIR/data/run/watchdog.lock"
flock -n 8 || exit 0
while true; do
  if [[ ! -f "$PARTS_ERP_DIR/data/run/maintenance" ]]; then
    PARTS_ERP_WATCHDOG=1 timeout 90 bash "$PARTS_ERP_DIR/deploy/termux/start.sh" 8>&- || true
  fi
  sleep 30 8>&-
done
