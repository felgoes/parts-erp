#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S9_HOST="${S9_HOST:-remote-host}"
S9_USER="${S9_USER:-deploy-user}"
S9_PORT="${S9_PORT:-8022}"
S9_APP_DIR="${S9_APP_DIR:-parts-erp}"
SSH_OPTS=(-p "$S9_PORT" -o BatchMode=yes -o ConnectTimeout=10)
[[ -z "${S9_IDENTITY_FILE:-}" ]] || SSH_OPTS+=(-i "$S9_IDENTITY_FILE")
REMOTE="$S9_USER@$S9_HOST"

[[ -z "$(git -C "$ROOT_DIR" status --porcelain)" ]] || { echo "Deploy exige commit limpo." >&2; exit 1; }
git -C "$ROOT_DIR" branch -r --contains HEAD | grep -q origin/ || { echo "Publique o commit antes do deploy." >&2; exit 1; }
[[ -x "$ROOT_DIR/frontend/node_modules/.bin/ng" ]] || { echo "Rode npm ci em frontend." >&2; exit 1; }

VERSION="$(git -C "$ROOT_DIR" rev-parse --short HEAD)"
STAGE=".deploy-$VERSION-frontend"
LOCAL_STAGE="$(mktemp -d "${TMPDIR:-/tmp}/parts-erp-frontend-$VERSION.XXXXXX")"
trap 'rm -rf "$LOCAL_STAGE"' EXIT
mkdir -p "$LOCAL_STAGE/site"

(cd "$ROOT_DIR/frontend" && npm run build -- --configuration production)
SITE_SOURCE="$ROOT_DIR/frontend/dist/frontend/browser"
[[ -s "$SITE_SOURCE/index.html" ]] || { echo "Build frontend sem index.html." >&2; exit 1; }
cp -a "$SITE_SOURCE/." "$LOCAL_STAGE/site/"

ssh "${SSH_OPTS[@]}" "$REMOTE" bash -s -- "$S9_APP_DIR" "$STAGE" <<'PREP'
set -euo pipefail
[[ "$2" =~ ^\.deploy-[a-f0-9]+-frontend$ ]]
APP="$(realpath -m "$HOME/$1")"
[[ "$APP" == "$HOME"/* && "$APP" != "$HOME" ]]
mkdir -p "$APP/data/$2/site"
PREP
tar -C "$LOCAL_STAGE" -cf - site | ssh "${SSH_OPTS[@]}" "$REMOTE" "tar -xf - -C \$HOME/$S9_APP_DIR/data/$STAGE"

ssh "${SSH_OPTS[@]}" "$REMOTE" bash -s -- "$S9_APP_DIR" "$STAGE" "$VERSION" <<'DEPLOY'
set -euo pipefail
APP="$(realpath -m "$HOME/$1")"
STAGE="$2"
VERSION="$3"
[[ "$APP" == "$HOME"/* && "$APP" != "$HOME" ]]
[[ "$STAGE" =~ ^\.deploy-[a-f0-9]+-frontend$ ]]
SITE="$APP/data/$STAGE/site"
CURRENT="$APP/frontend/dist/frontend/browser"
[[ -s "$SITE/index.html" && -d "$CURRENT" ]]
MAIN="$(grep -oE 'main-[A-Z0-9]+\.js' "$SITE/index.html" | head -n 1)"
[[ -n "$MAIN" && -s "$SITE/$MAIN" ]]

mkdir -p "$APP/data/backups"
NOW="$(date +%Y%m%d-%H%M%S)"
tar -czf "$APP/data/backups/frontend-$NOW-$VERSION.tar.gz" -C "$APP" frontend/dist/frontend
chmod 600 "$APP/data/backups/frontend-$NOW-$VERSION.tar.gz"

NEXT="$APP/frontend/dist/frontend/browser.next-$VERSION"
OLD="$APP/data/backups/frontend-browser-pre-$NOW"
[[ ! -e "$NEXT" && ! -e "$OLD" ]]
mv "$SITE" "$NEXT"
mv "$CURRENT" "$OLD"
if ! mv "$NEXT" "$CURRENT"; then
  mv "$OLD" "$CURRENT"
  exit 1
fi

if ! curl --fail --silent http://127.0.0.1:8000/health >/dev/null ||
   ! curl --fail --silent http://127.0.0.1:8080/ | grep -q "$MAIN" ||
   [[ ! -s "$CURRENT/$MAIN" ]]; then
  mv "$CURRENT" "$APP/data/backups/frontend-failed-$NOW"
  mv "$OLD" "$CURRENT"
  echo "Health check falhou; frontend anterior restaurado." >&2
  exit 1
fi

rm -rf "$APP/data/$STAGE"
echo "Frontend publicado: $VERSION; backup preservado."
DEPLOY
