#!/usr/bin/env bash
# Teto de tamanho de arquivo (catraca): nenhum arquivo novo pode nascer grande e os que já
# são grandes não podem crescer. É o que impede o custo de leitura de voltar a subir —
# depende de regra executada, não de disciplina de quem lê.
#
#   ./scripts/dev/structure-gate.sh          # verifica (portão)
#   ./scripts/dev/structure-gate.sh --update # regrava a linha de base depois de um split
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CAP="${PARTS_ERP_FILE_LINE_CAP:-400}"
BASELINE="$ROOT/scripts/dev/structure-baseline.txt"
EXTENSIONS=(py ts html scss)
EXCLUDES=(-path '*/node_modules/*' -o -path '*/.venv/*' -o -path '*/dist/*' -o -path '*/.angular/*')

collect() {
  local find_expr=()
  local first=1
  for ext in "${EXTENSIONS[@]}"; do
    [ "$first" -eq 1 ] || find_expr+=(-o)
    find_expr+=(-name "*.$ext")
    first=0
  done
  find "$ROOT/backend/app" "$ROOT/backend/tests" "$ROOT/frontend/src" \
    -type f \( "${find_expr[@]}" \) ! \( "${EXCLUDES[@]}" \) -exec wc -l {} + 2>/dev/null \
    | awk -v root="$ROOT/" '{ n=$2; sub(root, "", n); if (n != "" && $1+0 > 0 && n != "total") print $1, n }' \
    | sort -k2
}

oversized() { collect | awk -v cap="$CAP" '$1 > cap'; }

if [ "${1:-}" = "--update" ]; then
  oversized | sort -k1,1nr > "$BASELINE"
  echo "linha de base regravada com $(wc -l < "$BASELINE") arquivo(s) acima de $CAP linhas."
  exit 0
fi

if [ ! -f "$BASELINE" ]; then
  echo "linha de base ausente; rode ./scripts/dev/structure-gate.sh --update"
  exit 2
fi

new_offenders=""
grew=""
while read -r lines path; do
  current="$(collect | awk -v p="$path" '$2 == p { print $1 }')"
  registered="$(awk -v p="$path" '$2 == p { print $1 }' "$BASELINE")"
  if [ -z "$registered" ]; then
    new_offenders+="  $path ($lines linhas)"$'\n'
  elif [ -n "$current" ] && [ "$current" -gt "$registered" ]; then
    grew+="  $path ($registered -> $current linhas)"$'\n'
  fi
done < <(oversized)

if [ -n "$new_offenders" ]; then
  echo "arquivo(s) novo(s) acima de $CAP linhas — divida antes de publicar:" >&2
  printf '%s' "$new_offenders" >&2
  exit 1
fi

if [ -n "$grew" ]; then
  echo "arquivo(s) da linha de base que cresceram — o teto vale ao contrário:" >&2
  printf '%s' "$grew" >&2
  exit 1
fi

echo "estrutura ok: nenhum arquivo novo acima de $CAP linhas e nenhum da linha de base cresceu."
echo "na fila de divisão: $(wc -l < "$BASELINE") arquivo(s) legado(s)."
