#!/usr/bin/env bash
# Prepara o ambiente da máquina (uma vez por PC; depois é incremental).
#
#   ./scripts/setup-local.sh               # instala o que faltar; pula npm ci se o lockfile não mudou
#   ./scripts/setup-local.sh --force-deps  # reinstala as dependências do frontend do zero
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3.12}"
NODE_VERSION="$(tr -d '[:space:]' < "$ROOT_DIR/.nvmrc")"
NPM_VERSION="11.19.0"
FORCE_DEPS=0
[[ "${1:-}" == "--force-deps" ]] && FORCE_DEPS=1
# O script roda fora de shell interativo: carrega o nvm sozinho quando o Node não está no PATH.
if ! command -v node >/dev/null 2>&1 && [ -s "$HOME/.nvm/nvm.sh" ]; then
  # shellcheck disable=SC1091
  . "$HOME/.nvm/nvm.sh" >/dev/null 2>&1 || true
  if [ -f "$ROOT_DIR/.nvmrc" ]; then nvm use >/dev/null 2>&1 || true; fi
fi
command -v "$PYTHON" >/dev/null || { echo "Python 3.12 não encontrado." >&2; exit 1; }
python_version="$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
[[ "$python_version" == "3.12" ]] || { echo "Esperado Python 3.12; encontrado $python_version." >&2; exit 1; }
command -v node >/dev/null || { echo "Node.js ausente; instale a versão indicada em .nvmrc." >&2; exit 1; }
actual_node="$(node -p 'process.versions.node')"
[[ "$actual_node" == "$NODE_VERSION" ]] || { echo "Esperado Node.js $NODE_VERSION; encontrado $actual_node. Rode nvm install && nvm use." >&2; exit 1; }
actual_npm="$(npm --version)"
[[ "$actual_npm" == "$NPM_VERSION" ]] || { echo "Esperado npm $NPM_VERSION; encontrado $actual_npm." >&2; exit 1; }
python_bin="$ROOT_DIR/backend/.venv/bin/python"
if [[ ! -x "$python_bin" ]]; then "$PYTHON" -m venv "$ROOT_DIR/backend/.venv"; fi
"$python_bin" -m pip install --upgrade pip
"$python_bin" -m pip install -e "$ROOT_DIR/backend[dev]"

# npm ci apaga e reinstala node_modules (~30 s). Só vale quando o lockfile mudou; o resto
# do tempo ele é tempo perdido no meio da esteira.
lock_hash="$(sha256sum "$ROOT_DIR/frontend/package-lock.json" | cut -d' ' -f1)"
stamp="$ROOT_DIR/frontend/node_modules/.parts-erp-lock"
if [[ "$FORCE_DEPS" -eq 0 && -d "$ROOT_DIR/frontend/node_modules" && -f "$stamp" && "$(cat "$stamp")" == "$lock_hash" ]]; then
  echo "Frontend já instalado para este lockfile; pulando npm ci (use --force-deps para forçar)."
else
  (cd "$ROOT_DIR/frontend" && npm ci)
  printf '%s' "$lock_hash" > "$stamp"
fi
echo "Ambiente pronto. Configure backend/.env localmente antes de iniciar a API."
