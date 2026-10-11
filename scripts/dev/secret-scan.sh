#!/usr/bin/env bash
# Varredura de segredo antes do push (o repositório é privado, mas segredo versionado é
# segredo vazado: histórico é permanente e o clone vive em cada PC e no S9).
#
#   ./scripts/dev/secret-scan.sh            # arquivos do repositório + o que o push levaria
#   ./scripts/dev/secret-scan.sh --history  # também varre o histórico completo (mais lento)
#
# Nunca imprime valor: só o tipo de padrão e o arquivo:linha (ou a contagem, no diff).
# Sai com 1 quando encontra algo, para o `sync.sh finish` barrar a publicação.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE="${PARTS_ERP_BRANCH:-main}"
REMOTE="${PARTS_ERP_REMOTE:-origin}"
SCAN_HISTORY=0
[[ "${1:-}" == "--history" ]] && SCAN_HISTORY=1

PATTERNS=(
  "chave-privada|-----BEGIN [A-Z ]*PRIVATE KEY-----"
  "token-github|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
  "chave-aws|AKIA[0-9A-Z]{16}"
  "token-slack|xox[baprs]-[A-Za-z0-9-]{8,}"
  "chave-fernet|gAAAAA[A-Za-z0-9_-]{20,}"
  "token-jwt|eyJhbGciOi[A-Za-z0-9._-]{20,}"
  "senha-ou-secret-literal|(password|passwd|senha|secret|api[_-]?key|token)[[:space:]]*[=:][[:space:]]*[\"'][^\"']{12,}"
  "metadados-s9|S9_(HOST|USER|APP_DIR)=[^\\$\"']"
)

found=0
# Valor de teste (senha/token de mentira em teste ou fixture) é aviso, não bloqueio: o que
# barra a publicação é segredo em arquivo de produção, configuração ou documentação.
report_tree() {
  local label="$1" regex="$2" hits file
  hits="$(git -C "$ROOT" grep -lIE -e "$regex" -- . 2>/dev/null | grep -vE 'package-lock|\.min\.' || true)"
  [ -n "$hits" ] || return 0
  while IFS= read -r file; do
    case "$file" in
      *tests/* | *.spec.ts | *fixtures/*)
        echo "  aviso    $label em $file (valor de teste? confira antes de publicar)"
        ;;
      *)
        found=1
        echo "  ATENÇÃO  $label em $file"
        ;;
    esac
  done <<< "$hits"
}

echo "varrendo o repositório (arquivos versionados):"
for entry in "${PATTERNS[@]}"; do
  report_tree "${entry%%|*}" "${entry#*|}"
done
[ "$found" -eq 0 ] && echo "  ok       nenhum padrão de segredo nos arquivos versionados"

echo "varrendo o que este push levaria (diff contra $REMOTE/$BASE):"
diff_found=0
for entry in "${PATTERNS[@]}"; do
  regex="${entry#*|}"
  count="$(git -C "$ROOT" diff "$REMOTE/$BASE" -- . 2>/dev/null | grep -E '^\+' | grep -cIE -e "$regex" || true)"
  if [ "${count:-0}" -gt 0 ]; then
    diff_found=1
    found=1
    echo "  ATENÇÃO  ${entry%%|*}: $count linha(s) adicionada(s)"
  fi
done
[ "$diff_found" -eq 0 ] && echo "  ok       nada suspeito no diff"

if [ "$SCAN_HISTORY" -eq 1 ]; then
  # Auditoria, não portão: o histórico tem valor de teste e exemplo de documentação por
  # natureza, e o que já foi publicado não sai do histórico por varredura. Serve para
  # revisar de tempos em tempos; o portão é a árvore e o diff acima.
  echo "auditando o histórico completo (contagens por tipo, para revisão manual):"
  for entry in "${PATTERNS[@]}"; do
    count="$(git -C "$ROOT" log --all -p 2>/dev/null | grep -cIE -e "${entry#*|}" || true)"
    [ "${count:-0}" -gt 0 ] && echo "  revisar  ${entry%%|*}: $count ocorrência(s) (esperado em teste/exemplo; confira se há valor real)"
  done
  echo "  (auditoria de histórico concluída — não bloqueia a publicação)"
fi

if [ "$found" -ne 0 ]; then
  echo "segredo detectado: revogue no emissor antes de publicar (apagar do último commit não limpa o histórico)." >&2
  exit 1
fi
echo "scan de segredo ok."
