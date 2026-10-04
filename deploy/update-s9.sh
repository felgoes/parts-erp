#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S9_HOST="${S9_HOST:-remote-host}"
S9_USER="${S9_USER:-deploy-user}"
S9_PORT="${S9_PORT:-8022}"
S9_APP_DIR="${S9_APP_DIR:-parts-erp}"
SSH_OPTS=(-p "$S9_PORT" -o BatchMode=yes -o ConnectTimeout=10)
REMOTE="$S9_USER@$S9_HOST"

if [[ -n "${S9_IDENTITY_FILE:-}" ]]; then
  SSH_OPTS+=(-i "$S9_IDENTITY_FILE")
elif [[ -f "$HOME/.ssh/id_ed25519" ]]; then
  SSH_OPTS+=(-i "$HOME/.ssh/id_ed25519")
fi

if [[ -n "$(git -C "$ROOT_DIR" status --porcelain --untracked-files=normal)" ]]; then
  echo "O deploy exige um commit limpo para que código e frontend tenham a mesma versão." >&2
  exit 1
fi
if [[ ! -x "$ROOT_DIR/frontend/node_modules/.bin/ng" ]]; then
  echo "Dependências do frontend ausentes. Rode: (cd frontend && npm ci)" >&2
  exit 1
fi

LOCAL_PYTHON="$(command -v python3 || command -v python)"
echo "Compilando frontend localmente..."
(cd "$ROOT_DIR/frontend" && npm run build)

BUILD_VERSION="$(git -C "$ROOT_DIR" rev-parse --short HEAD)"
BUILD_INDEX="$ROOT_DIR/frontend/dist/frontend/browser/index.html"
BUILD_VERSION="$BUILD_VERSION" BUILD_INDEX="$BUILD_INDEX" "$LOCAL_PYTHON" - <<'PY'
import os
import re
from pathlib import Path

path = Path(os.environ["BUILD_INDEX"])
version = os.environ["BUILD_VERSION"]
html = path.read_text(encoding="utf-8")
html = re.sub(r'(\b(?:src|href)="[^"]+\.(?:js|css))(?:\?v=[^"]*)?"', rf'\1?v={version}"', html)
path.write_text(html, encoding="utf-8")
PY

echo "Transferindo a versão $BUILD_VERSION para o S9..."
ssh "${SSH_OPTS[@]}" "$REMOTE" bash -s -- "$S9_APP_DIR" <<'PREPARE_REMOTE'
set -euo pipefail
APP_ARG="$1"
if [[ "$APP_ARG" = /* ]]; then
  APP_DIR="$APP_ARG"
else
  APP_DIR="$HOME/$APP_ARG"
fi
APP_DIR="$(realpath -m "$APP_DIR")"
if [[ "$APP_DIR" != "$HOME"/* ]] || [[ "$APP_DIR" == "$HOME" ]]; then
  echo "Diretório de aplicação recusado: $APP_DIR" >&2
  exit 1
fi

mkdir -p "$APP_DIR/data/backups"
if [[ -x "$APP_DIR/deploy/termux/stop.sh" ]]; then
  PARTS_ERP_DIR="$APP_DIR" "$APP_DIR/deploy/termux/stop.sh" || true
fi

if [[ -f "$APP_DIR/data/parts-erp.db" ]]; then
  backup="$APP_DIR/data/backups/parts-erp-$(date +%Y%m%d-%H%M%S).db"
  if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$APP_DIR/data/parts-erp.db" ".backup '$backup'"
  else
    cp "$APP_DIR/data/parts-erp.db" "$backup"
  fi
  echo "Backup do banco criado antes da atualização."
fi

# Código é recuperável pelo Git. Dados, documentos, .env e virtualenv são preservados.
rm -rf \
  "$APP_DIR/backend/app" \
  "$APP_DIR/backend/alembic/versions" \
  "$APP_DIR/deploy/termux"
PREPARE_REMOTE

git -C "$ROOT_DIR" archive --format=tar HEAD | \
  ssh "${SSH_OPTS[@]}" "$REMOTE" "tar -xf - -C '$S9_APP_DIR'"
tar -C "$ROOT_DIR/frontend/dist/frontend" -cf - . | \
  ssh "${SSH_OPTS[@]}" "$REMOTE" \
    "rm -rf '$S9_APP_DIR/frontend/dist/frontend' && mkdir -p '$S9_APP_DIR/frontend/dist/frontend' && tar -xf - -C '$S9_APP_DIR/frontend/dist/frontend'"

echo "Aplicando migrações e reiniciando..."
ssh "${SSH_OPTS[@]}" "$REMOTE" bash -s -- "$S9_APP_DIR" <<'REMOTE_SCRIPT'
set -euo pipefail
APP_ARG="$1"
if [[ "$APP_ARG" = /* ]]; then
  APP_DIR="$APP_ARG"
else
  APP_DIR="$HOME/$APP_ARG"
fi
APP_DIR="$(realpath -m "$APP_DIR")"
if [[ "$APP_DIR" != "$HOME"/* ]] || [[ "$APP_DIR" == "$HOME" ]]; then
  echo "Diretório de aplicação recusado: $APP_DIR" >&2
  exit 1
fi
cd "$APP_DIR"

VENV="$APP_DIR/backend/.venv-termux"
HASH_FILE="$APP_DIR/data/.backend-deps-hash"
deps_hash="$(sha256sum "$APP_DIR/backend/pyproject.toml" | awk '{print $1}')"
old_hash="$(cat "$HASH_FILE" 2>/dev/null || true)"
if [[ ! -x "$VENV/bin/python" ]]; then
  python -m venv --system-site-packages "$VENV"
fi
if [[ "$deps_hash" != "$old_hash" ]] || ! "$VENV/bin/python" -c 'import app' 2>/dev/null; then
  "$VENV/bin/python" -m pip install \
    --extra-index-url https://termux-user-repository.github.io/pypi/ ./backend
  printf '%s\n' "$deps_hash" >"$HASH_FILE"
fi

if ! grep -q '^WEBHOOK_SHARED_SECRET=' backend/.env; then
  webhook_secret="$(python -c 'import secrets; print(secrets.token_hex(32))')"
  printf '\nWEBHOOK_SHARED_SECRET=%s\n' "$webhook_secret" >>backend/.env
fi
grep -q '^WEBHOOK_MAX_BODY_BYTES=' backend/.env || \
  printf 'WEBHOOK_MAX_BODY_BYTES=131072\n' >>backend/.env
grep -q '^TELEMETRY_RATE_LIMIT_PER_MINUTE=' backend/.env || \
  printf 'TELEMETRY_RATE_LIMIT_PER_MINUTE=60\n' >>backend/.env
grep -q '^LOGIN_RATE_LIMIT_ATTEMPTS=' backend/.env || \
  printf 'LOGIN_RATE_LIMIT_ATTEMPTS=5\n' >>backend/.env
grep -q '^LOGIN_RATE_LIMIT_WINDOW_SECONDS=' backend/.env || \
  printf 'LOGIN_RATE_LIMIT_WINDOW_SECONDS=300\n' >>backend/.env
grep -q '^PUBLIC_SITE_URL=' backend/.env || \
  printf 'PUBLIC_SITE_URL=https://goesautoparts.com.br\n' >>backend/.env
chmod 600 backend/.env

sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__PREFIX__|$PREFIX|g" -e "s|__HOME__|$HOME|g" \
  deploy/termux/nginx.conf.in >deploy/termux/nginx.conf
sed -e "s|__APP_DIR__|$APP_DIR|g" \
  deploy/termux/redis.conf.in >deploy/termux/redis.conf
chmod +x deploy/termux/*.sh

(cd backend && "$VENV/bin/alembic" upgrade head)
PARTS_ERP_DIR="$APP_DIR" bash deploy/termux/start.sh
health="$(curl --fail --silent http://127.0.0.1:8000/health)"
[[ "$health" == '{"status":"ok"}' ]]
echo "Parts ERP atualizado na porta 8080; backup preservado em data/backups."
REMOTE_SCRIPT

echo "Atualização concluída."
