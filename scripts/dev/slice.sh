#!/usr/bin/env bash
# Fatia de um arquivo em vez do arquivo inteiro: uma função, um bloco, um trecho.
#
#   ./scripts/dev/slice.sh backend/app/api/routes/purchases.py "def receive_purchase" 40
#   ./scripts/dev/slice.sh frontend/src/app/pages/purchases/purchases.html "Abrir meu perfil"
#
# Imprime o trecho com número de linha, o tamanho do resultado e o custo aproximado em
# tokens — para o agente saber exatamente o que pagou por ler.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FILE="${1:-}"
PATTERN="${2:-}"
AFTER="${3:-35}"
BEFORE="${4:-3}"

if [ -z "$FILE" ] || [ -z "$PATTERN" ]; then
  sed -n '/^# Fatia/,/^set -euo/p' "${BASH_SOURCE[0]}" | sed -e 's/^# \{0,1\}//' -e '/^set -euo/d'
  exit 2
fi

target="$ROOT/$FILE"
[ -f "$target" ] || { echo "arquivo não encontrado: $FILE" >&2; exit 2; }

total_lines=$(wc -l < "$target")
out="$(grep -n -B "$BEFORE" -A "$AFTER" -e "$PATTERN" "$target" | head -200 || true)"

if [ -z "$out" ]; then
  echo "nenhuma linha casou com '$PATTERN' em $FILE ($total_lines linhas)." >&2
  echo "dica: rode ./scripts/dev/code-map.sh ${FILE%%/*} para ver os arquivos da área." >&2
  exit 1
fi

printf '%s\n' "$out"
matched_lines=$(printf '%s\n' "$out" | wc -l)
chars=$(printf '%s\n' "$out" | wc -c)
printf '\n[%s: %s de %s linhas | %s caracteres (~%s tokens) em vez de ~%s tokens do arquivo inteiro]\n' \
  "$FILE" "$matched_lines" "$total_lines" "$chars" "$((chars / 4))" "$(( $(wc -c < "$target") / 4 ))"
