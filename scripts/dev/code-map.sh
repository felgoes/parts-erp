#!/usr/bin/env bash
# Mapa do código com custo de leitura: para o agente começar por aqui em vez de explorar
# o repositório com dezenas de buscas.
#
#   ./scripts/dev/code-map.sh              # mapa completo (arquivos grandes primeiro)
#   ./scripts/dev/code-map.sh pagamentos   # filtra por trecho do caminho
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FILTER="${1:-}"

list_files() {
  find "$ROOT/backend/app" "$ROOT/backend/tests" "$ROOT/frontend/src" -type f \
    \( -name '*.py' -o -name '*.ts' -o -name '*.html' -o -name '*.scss' \) \
    ! -path '*/node_modules/*' ! -path '*/.venv/*' ! -path '*/dist/*' ! -path '*/.angular/*'
}

printf '%-58s %6s %8s\n' "arquivo" "linhas" "~tokens"
list_files | while read -r file; do
  rel="${file#"$ROOT"/}"
  if [ -n "$FILTER" ] && [[ "$rel" != *"$FILTER"* ]]; then continue; fi
  lines=$(wc -l < "$file")
  # ~3,6 caracteres por token em código, a mesma razão com que eu planejo contexto.
  tokens=$(( $(wc -c < "$file") / 4 ))
  printf '%-58s %6s %8s\n' "$rel" "$lines" "$tokens"
done | sort -k3,3nr
