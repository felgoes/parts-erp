#!/usr/bin/env bash
# Verificações do Parts ERP no WSL — porta de entrada única da esteira.
#
#   ./scripts/dev/checks.sh backend                        # compila e roda toda a suíte do backend
#   ./scripts/dev/checks.sh backend test_purchase_import   # só o que casar (nome ou arquivo)
#   ./scripts/dev/checks.sh frontend                       # roda todos os testes do frontend
#   ./scripts/dev/checks.sh frontend src/app/shared/purchase-import-math.spec.ts
#   ./scripts/dev/checks.sh frontend buildImportPlan       # filtro por nome de suíte/teste
#   ./scripts/dev/checks.sh build                          # build de produção do frontend
#   ./scripts/dev/checks.sh all                            # portão completo antes do push
#
# Sem filtro roda tudo; com filtro roda só o trecho que interessa — é o modo de iterar
# durante a implementação. O portão antes do push é sempre `all`.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV_PY="$BACKEND/.venv/bin/python"

say() { printf '%s\n' "$*"; }
fail() { printf 'erro: %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '/^# Verificações/,/^set -euo/p' "${BASH_SOURCE[0]}" | sed -e 's/^# \{0,1\}//' -e '/^set -euo/d'
}

ensure_node() {
  if ! command -v npm >/dev/null 2>&1 && [ -s "$HOME/.nvm/nvm.sh" ]; then
    # shellcheck disable=SC1091
    . "$HOME/.nvm/nvm.sh" >/dev/null 2>&1 || true
  fi
  command -v npm >/dev/null 2>&1 || fail "npm não encontrado. Instale o Node via nvm (veja docs/development-setup.md)."
}

run_backend() {
  local filter="${1:-}"
  [ -x "$VENV_PY" ] || fail "ambiente Python ausente em backend/.venv. Rode ./scripts/setup-local.sh."
  (cd "$BACKEND" && "$VENV_PY" -m compileall -q app) || fail "compileall reprovou."
  if [ -z "$filter" ]; then
    say "→ backend: suíte completa"
    (cd "$BACKEND" && "$VENV_PY" -m pytest -q)
    return
  fi
  case "$filter" in
    */* | *.py)
      say "→ backend: $filter"
      (cd "$BACKEND" && "$VENV_PY" -m pytest -q "$filter")
      ;;
    *)
      say "→ backend: -k $filter"
      (cd "$BACKEND" && "$VENV_PY" -m pytest -q -k "$filter")
      ;;
  esac
}

run_frontend() {
  local filter="${1:-}"
  ensure_node
  [ -d "$FRONTEND/node_modules" ] || fail "dependências do frontend ausentes. Rode ./scripts/setup-local.sh."
  local args=() log
  log="$(mktemp)"
  trap 'rm -f "$log"' RETURN
  if [ -z "$filter" ]; then
    say "→ frontend: suíte completa"
  else
    case "$filter" in
      */* | *.ts)
        say "→ frontend: $filter"
        args=(--include "$filter")
        ;;
      *)
        say "→ frontend: --filter $filter"
        args=(--filter "$filter")
        ;;
    esac
  fi
  (cd "$FRONTEND" && npx ng test --watch=false "${args[@]+"${args[@]}"}") 2>&1 | tee "$log"
  # Filtro que não casa nada não pode virar portão verde: o runner sai com 0 e tudo "skipped".
  local ran
  ran="$(sed -e 's/\x1b\[[0-9;]*m//g' "$log" | grep -Eo 'Tests +[0-9]+ passed' | head -1 | grep -Eo '[0-9]+' || true)"
  if [ -z "$ran" ] || [ "$ran" -eq 0 ]; then
    fail "nenhum teste executou no frontend (filtro sem correspondência?). Rode sem filtro ou ajuste o nome."
  fi
}

run_build() {
  ensure_node
  say "→ frontend: build de produção"
  (cd "$FRONTEND" && npm run build -- --configuration production)
}

case "${1:-all}" in
  backend)
    shift || true
    run_backend "${1:-}"
    ;;
  frontend)
    shift || true
    run_frontend "${1:-}"
    ;;
  build) run_build ;;
  all)
    run_backend ""
    run_frontend ""
    run_build
    say "portão completo ok: backend + frontend + build"
    ;;
  help | -h | --help)
    usage
    ;;
  *)
    usage
    exit 1
    ;;
esac
