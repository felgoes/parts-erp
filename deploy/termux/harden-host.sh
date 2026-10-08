#!/data/data/com.termux/files/usr/bin/bash
# Infrastructure-only installation; preserves existing app and database.
set -euo pipefail
export PREFIX=/data/data/com.termux/files/usr
export PATH="$PREFIX/bin:$PATH"
export SVDIR="$PREFIX/var/service"
APP_DIR="${PARTS_ERP_DIR:-$HOME/parts-erp}"
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP="$APP_DIR/data/backups/hardening-$(date +%Y%m%d-%H%M%S)"
umask 077
mkdir -p "$BACKUP"
cp -a "$APP_DIR/deploy/termux" "$BACKUP/termux"
cp -a "$HOME/.termux/boot" "$BACKUP/boot"
cp -a "$PREFIX/etc/ssh/sshd_config" "$BACKUP/sshd_config"
test -s "$HOME/.ssh/authorized_keys"
for name in start.sh stop.sh monitor-loop.sh watchdog-service.sh; do
  bash -n "$SOURCE_DIR/$name"
  if [[ "$SOURCE_DIR" != "$APP_DIR/deploy/termux" ]]; then
    install -m 700 "$SOURCE_DIR/$name" "$APP_DIR/deploy/termux/$name"
  fi
done

# First-value-wins SSH settings: prepend, then validate before reloading.
{
  printf '%s\n' 'PasswordAuthentication no' 'KbdInteractiveAuthentication no' \
    'PubkeyAuthentication yes' 'MaxAuthTries 3' 'LoginGraceTime 30' \
    'MaxStartups 10:30:30' 'ClientAliveInterval 60' 'ClientAliveCountMax 3'
  cat "$BACKUP/sshd_config"
} >"$PREFIX/etc/ssh/sshd_config"
if ! sshd -t; then
  cp "$BACKUP/sshd_config" "$PREFIX/etc/ssh/sshd_config"
  exit 1
fi

# Tunnel is the sole HTTP ingress. Preserve all existing routes and limits.
NGINX="$APP_DIR/deploy/termux/nginx.conf"
sed -i 's/listen 0\.0\.0\.0:8080;/listen 127.0.0.1:8080;/g' "$NGINX"
if ! grep -q 'server_tokens off;' "$NGINX"; then
  sed -i '/^http {/a\  server_tokens off;\n  client_header_timeout 15s;\n  client_body_timeout 30s;\n  send_timeout 30s;' "$NGINX"
fi
# Both virtual hosts proxy /api/: enforce the same login limit on both hosts.
if ! grep -q 'zone=auth_shared:' "$NGINX"; then
  sed -i '/^http {/a\  map $uri $auth_limit_key { default ""; /api/v1/auth/login $http_cf_connecting_ip; }\n  limit_req_zone $auth_limit_key zone=auth_shared:1m rate=5r/m;\n  limit_req zone=auth_shared burst=5 nodelay;\n  limit_req_status 429;' "$NGINX"
fi
if ! nginx -t -c "$NGINX"; then
  cp "$BACKUP/termux/nginx.conf" "$NGINX"
  cp "$BACKUP/sshd_config" "$PREFIX/etc/ssh/sshd_config"
  exit 1
fi
nginx -s reload -c "$NGINX"

mkdir -p "$SVDIR/parts-erp-watchdog/log" "$PREFIX/var/log/sv/parts-erp-watchdog"
cat >"$SVDIR/parts-erp-watchdog/run" <<'RUN'
#!/data/data/com.termux/files/usr/bin/sh
exec 2>&1
exec /data/data/com.termux/files/home/parts-erp/deploy/termux/watchdog-service.sh
RUN
cat >"$SVDIR/parts-erp-watchdog/log/run" <<'LOG'
#!/data/data/com.termux/files/usr/bin/sh
exec svlogd -tt /data/data/com.termux/files/usr/var/log/sv/parts-erp-watchdog
LOG
printf 's1048576\nn5\n' >"$PREFIX/var/log/sv/parts-erp-watchdog/config"
chmod 700 "$SVDIR/parts-erp-watchdog/run" "$SVDIR/parts-erp-watchdog/log/run"
cat >"$HOME/.termux/boot/parts-erp" <<'BOOT'
#!/data/data/com.termux/files/usr/bin/sh
export PREFIX=/data/data/com.termux/files/usr
export PATH="$PREFIX/bin:$PATH"
export SVDIR="$PREFIX/var/service"
termux-wake-lock >/dev/null 2>&1 || true
# Start runsvdir first; sv alone cannot start a missing supervisor.
. "$PREFIX/etc/profile.d/start-services.sh"
BOOT
chmod 700 "$HOME/.termux/boot/parts-erp"
sv-enable sshd
service-daemon start
sv-enable parts-erp-watchdog
sleep 3
sv up parts-erp-watchdog
# Restart only the lightweight monitor to load the new bounded loop.
if [[ -f "$APP_DIR/data/run/monitor.pid" ]]; then
  monitor_pid="$(cat "$APP_DIR/data/run/monitor.pid")"
  if [[ "$monitor_pid" =~ ^[0-9]+$ ]] &&
     tr '\0' ' ' <"/proc/$monitor_pid/cmdline" 2>/dev/null | grep -Fq "$APP_DIR/deploy/termux/monitor-loop.sh"; then
    kill -TERM "$monitor_pid"
  fi
fi
PARTS_ERP_WATCHDOG=1 bash "$APP_DIR/deploy/termux/start.sh"
# Reload SSH config without terminating authenticated sessions.
sshd_pid="$(cat "$PREFIX/var/run/sshd.pid")"
kill -HUP "$sshd_pid"
printf 'Backup: %s\n' "$BACKUP"
sv status sshd parts-erp-watchdog
curl -fsS --max-time 5 http://127.0.0.1:8000/health
