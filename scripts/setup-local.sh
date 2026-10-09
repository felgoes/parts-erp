#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3.12}"
NODE_VERSION="$(tr -d '[:space:]' < "$ROOT_DIR/.nvmrc")"
NPM_VERSION="11.19.0"
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
(cd "$ROOT_DIR/frontend" && npm ci)
echo "Ambiente pronto. Configure backend/.env localmente antes de iniciar a API."
