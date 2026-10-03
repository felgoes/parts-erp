#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S9_HOST="${S9_HOST:-[private-host]}"
S9_USER="${S9_USER:-[deploy-user]}"
S9_PORT="${S9_PORT:-8022}"
S9_APP_DIR="${S9_APP_DIR:-/srv/parts-erp}"
SSH_OPTS=(-p "$S9_PORT" -o BatchMode=yes)
REMOTE="$S9_USER@$S9_HOST"

if [[ -n "${S9_IDENTITY_FILE:-}" ]]; then
  SSH_OPTS+=(-i "$S9_IDENTITY_FILE")
fi

if [[ -z "${S9_IDENTITY_FILE:-}" && -f "$HOME/.ssh/id_ed25519" ]]; then
  SSH_OPTS+=(-i "$HOME/.ssh/id_ed25519")
fi

if [[ ! -x "$ROOT_DIR/frontend/node_modules/.bin/ng" ]]; then
  echo "Dependências do frontend ausentes. Rode: (cd frontend && npm ci)" >&2
  exit 1
fi

echo "Compilando frontend localmente..."
(cd "$ROOT_DIR/frontend" && npm run build)

echo "Atualizando código no S9..."
ssh "${SSH_OPTS[@]}" "$REMOTE" "cd '$S9_APP_DIR' && git pull --ff-only origin main"

echo "Transferindo frontend já compilado..."
tar -C "$ROOT_DIR/frontend/dist/frontend" -cf - . | \
  ssh "${SSH_OPTS[@]}" "$REMOTE" "rm -rf '$S9_APP_DIR/frontend/dist/frontend' && mkdir -p '$S9_APP_DIR/frontend/dist/frontend' && tar -xf - -C '$S9_APP_DIR/frontend/dist/frontend'"

echo "Aplicando migrações e reiniciando..."
ssh "${SSH_OPTS[@]}" "$REMOTE" bash -s -- "$S9_APP_DIR" <<'REMOTE_SCRIPT'
set -euo pipefail
APP_DIR="$1"
cd "$APP_DIR"

VENV="$APP_DIR/backend/.venv-termux"
HASH_FILE="$APP_DIR/data/.backend-deps-hash"
mkdir -p "$APP_DIR/data"

deps_hash="$(sha256sum "$APP_DIR/backend/pyproject.toml" | awk '{print $1}')"
old_hash="$(cat "$HASH_FILE" 2>/dev/null || true)"
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Venv ausente; instalando dependências Python..."
  python -m venv --system-site-packages "$VENV"
  "$VENV/bin/python" -m pip install --extra-index-url https://termux-user-repository.github.io/pypi/ ./backend
elif [[ -n "$old_hash" && "$deps_hash" != "$old_hash" ]]; then
  echo "Dependências Python alteradas; instalando no venv..."
  "$VENV/bin/python" -m pip install --extra-index-url https://termux-user-repository.github.io/pypi/ ./backend
else
  echo "Venv já funcional; instalação Python ignorada."
fi
printf '%s\n' "$deps_hash" > "$HASH_FILE"

cd "$APP_DIR/backend"
"$VENV/bin/alembic" upgrade head
cd "$APP_DIR"
bash deploy/termux/start.sh
curl --fail --silent http://127.0.0.1:8080/ >/dev/null
echo "Parts ERP atualizado na porta 8080"
REMOTE_SCRIPT

echo "Atualização concluída."
