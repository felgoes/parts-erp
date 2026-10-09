#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for name in S9_HOST S9_USER S9_PORT S9_APP_DIR S9_IDENTITY_FILE; do
[historical infra reference removed]
done
[historical infra reference removed]
[historical infra reference removed]
[historical infra reference removed]
chmod 600 "$S9_IDENTITY_FILE"
SSH_OPTS=(-p "$S9_PORT" -o BatchMode=yes -o ConnectTimeout=10); SSH_OPTS+=(-i "$S9_IDENTITY_FILE" -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes); REMOTE="$S9_USER@$S9_HOST"
ssh "${SSH_OPTS[@]}" "$REMOTE" true
[[ -z "$(git -C "$ROOT_DIR" status --porcelain)" ]] || { echo "Deploy exige commit limpo." >&2; exit 1; }
git -C "$ROOT_DIR" fetch --quiet origin main
EXPECTED="$(git -C "$ROOT_DIR" rev-parse origin/main)"
ACTUAL="$(git -C "$ROOT_DIR" rev-parse HEAD)"
[[ "$ACTUAL" == "$EXPECTED" ]] || { echo "Deploy bloqueado: checkout não está exatamente em origin/main ($ACTUAL != $EXPECTED)." >&2; exit 1; }
[[ -x "$ROOT_DIR/frontend/node_modules/.bin/ng" ]] || { echo "Rode npm ci em frontend." >&2; exit 1; }
VERSION="$(git -C "$ROOT_DIR" rev-parse --short HEAD)"; STAGE=".deploy-$VERSION"
LOCAL_STAGE="$(mktemp -d "${TMPDIR:-/tmp}/parts-erp-$VERSION.XXXXXX")"
trap 'rm -rf "$LOCAL_STAGE"' EXIT
mkdir -p "$LOCAL_STAGE/source" "$LOCAL_STAGE/site"
(cd "$ROOT_DIR/frontend" && npm run build -- --configuration production)
cp -a "$ROOT_DIR/frontend/dist/frontend/browser/." "$LOCAL_STAGE/site/"
git -C "$ROOT_DIR" archive --format=tar HEAD | tar -xf - -C "$LOCAL_STAGE/source"
test -s "$LOCAL_STAGE/site/index.html" && test -f "$LOCAL_STAGE/source/backend/app/main.py"
find "$LOCAL_STAGE/site" -maxdepth 1 -type f -name 'main-*.js' -size +0c -print -quit | grep -q . || { echo "Build sem bundle principal." >&2; exit 1; }
find "$LOCAL_STAGE/site" -maxdepth 1 -type f -name 'chunk-*.js' -size +0c -print -quit | grep -q . || { echo "Build sem chunks JavaScript." >&2; exit 1; }
ssh "${SSH_OPTS[@]}" "$REMOTE" bash -s -- "$S9_APP_DIR" "$STAGE" <<\PREP
set -euo pipefail; [[ "$2" =~ ^\.deploy-[a-f0-9]+$ ]]
APP="$(realpath -m "$HOME/$1")"; [[ "$APP" == "$HOME"/* && "$APP" != "$HOME" ]]
mkdir -p "$APP/data/$2"
PREP
tar -C "$LOCAL_STAGE" -cf - . | ssh "${SSH_OPTS[@]}" "$REMOTE" "tar -xf - -C \$HOME/$S9_APP_DIR/data/$STAGE"
ssh "${SSH_OPTS[@]}" "$REMOTE" bash -s -- "$S9_APP_DIR" "$STAGE" "$VERSION" <<\DEPLOY
set -euo pipefail
APP="$(realpath -m "$HOME/$1")"; STAGE="$2"; VERSION="$3"; [[ "$APP" == "$HOME"/* && "$APP" != "$HOME" ]]
[[ "$STAGE" =~ ^\.deploy-[a-f0-9]+$ ]]; S="$APP/data/$STAGE/source"; WEB="$APP/data/$STAGE/site"
[[ -s "$WEB/index.html" && -f "$S/backend/app/main.py" ]]
cd "$APP"
V="$APP/backend/.venv-termux"
[[ -x "$V/bin/python" ]] || { echo "Virtualenv Termux não encontrado; abortando antes da parada." >&2; exit 1; }
(cd "$APP/backend" && PYTHONPATH="$S/backend" "$V/bin/python" -c "import app.main")
mkdir -p "$APP/data/backups"; NOW="$(date +%Y%m%d-%H%M%S)"
tar -czf "$APP/data/backups/code-$NOW.tar.gz" -C "$APP" backend/app backend/alembic/versions backend/pyproject.toml frontend/dist/frontend deploy/termux; chmod 600 "$APP/data/backups/code-$NOW.tar.gz"
if [[ -f "$APP/data/parts-erp.db" ]]; then
  "$APP/backend/.venv-termux/bin/python" - "$APP/data/parts-erp.db" "$APP/data/backups/db-$NOW.sqlite" <<\BACKUP
import os, sqlite3, sys
s=sqlite3.connect("file:"+sys.argv[1]+"?mode=ro",uri=True); d=sqlite3.connect(sys.argv[2])
try: s.backup(d)
finally: d.close(); s.close()
os.chmod(sys.argv[2],0o600)
BACKUP
fi
[[ ! -f "$S/deploy/termux/stop.sh" ]] || PARTS_ERP_DIR="$APP" PARTS_ERP_PRESERVE_CLOUDFLARED=1 bash "$S/deploy/termux/stop.sh"
rm -rf "$APP/backend/app" "$APP/backend/alembic/versions"
cp -a "$S/backend/app" "$APP/backend/app"; cp -a "$S/backend/alembic/versions" "$APP/backend/alembic/versions"; cp -a "$S/backend/pyproject.toml" "$APP/backend/pyproject.toml"
mv "$APP/frontend/dist/frontend" "$APP/data/backups/frontend-pre-$NOW"
mkdir -p "$APP/frontend/dist/frontend/browser"
cp -a "$WEB/." "$APP/frontend/dist/frontend/browser/"
cp -a "$S/deploy/." "$APP/deploy/"
mkdir -p "$HOME/.termux/boot"
cp "$APP/deploy/termux/boot-parts-erp" "$HOME/.termux/boot/parts-erp"
chmod +x "$HOME/.termux/boot/parts-erp"
chmod 600 backend/.env
if [[ -f deploy/termux/redis.conf.in ]]; then sed "s|__APP_DIR__|$APP|g" deploy/termux/redis.conf.in >deploy/termux/redis.conf; fi
chmod +x deploy/termux/*.sh; (cd backend && "$V/bin/alembic" upgrade heads)
PARTS_ERP_DIR="$APP" bash deploy/termux/start.sh
[[ "$(curl --fail --silent http://127.0.0.1:8000/health)" == "{\"status\":\"ok\"}" ]]; curl --fail --silent http://127.0.0.1:8080/ >/dev/null
rm -rf "$S"; echo "Origin atualizado: $VERSION; aguardando verificações públicas."
DEPLOY


# A deploy is successful only when both customer-facing origins have recovered
# through Cloudflare. This catches Tunnel 1033 and origin errors that local checks miss.
probe_public_page() {
  local label="$1" url="$2" expected="$3" attempt status body bundle asset_status
  body="$LOCAL_STAGE/probe-$(printf '%s' "$label" | tr '[:upper:]' '[:lower:]').html"
  for attempt in {1..18}; do
    status="$(curl --silent --show-error --location --connect-timeout 8 --max-time 12 \
      --output "$body" --write-out '%{http_code}' "$url" 2>/dev/null || true)"
    if [[ "$status" == 200 ]] && grep -Fq "$expected" "$body"; then
      bundle="$(grep -oE 'src="[^"]*main-[^"]+\.js[^"]*"' "$body" | head -n 1 | cut -d '"' -f 2)"
      if [[ -n "$bundle" ]]; then
        asset_status="$(curl --silent --location --connect-timeout 8 --max-time 12 \
          --output "$LOCAL_STAGE/probe-bundle.js" --write-out '%{http_code}' \
          "${url%/}/${bundle#/}" 2>/dev/null || true)"
        if [[ "$asset_status" == 200 && -s "$LOCAL_STAGE/probe-bundle.js" ]]; then
          echo "Smoke público OK: $label (HTML e bundle JS HTTP 200; tentativa $attempt)."
          return 0
        fi
        status="HTML $status, bundle ${asset_status:-000}"
      else
        status="HTML $status, bundle principal ausente"
      fi
    fi
    echo "Aguardando recuperação pública de $label (tentativa $attempt/18; HTTP ${status:-000})."
    sleep 5
  done
  echo "Smoke público falhou para $label; deploy não pode ser considerado concluído." >&2
  return 1
}

probe_public_page "site" "${PARTS_ERP_PUBLIC_SITE_URL:-https://goesautoparts.com.br/}" "Goes Auto Parts"
probe_public_page "ERP" "${PARTS_ERP_PUBLIC_ERP_URL:-https://erp.goesautoparts.com.br/}" "Parts ERP | Gestão de estoque e vendas"
echo "Deploy e verificações públicas concluídos: $VERSION."
