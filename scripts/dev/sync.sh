#!/usr/bin/env bash
# Uma pessoa, duas máquinas: mantém o checkout canônico alinhado com o que está publicado.
#
#   ./scripts/dev/sync.sh status    # o que está publicado, o que é local e o que divergiu
#   ./scripts/dev/sync.sh start     # começa a trabalhar aqui (fetch + fast-forward; recusa trabalho local não publicado)
#   ./scripts/dev/sync.sh finish    # encerra nesta máquina (rebase se preciso + checks + push)
#   ./scripts/dev/sync.sh publish   # publica os commits locais sem rodar checks
#
# Regra de ouro do fluxo de duas máquinas: nenhuma máquina guarda commit sem publicar.
# `start` avisa quando há trabalho local não publicado e `finish` garante a publicação
# (com o portão de checks) antes de você trocar de PC. Nada aqui faz deploy: o deploy
# continua sendo o passo separado pelo wrapper privado, com smoke público.
set -euo pipefail
export GIT_TERMINAL_PROMPT=0

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BRANCH="${PARTS_ERP_BRANCH:-main}"
REMOTE="${PARTS_ERP_REMOTE:-origin}"

say() { printf '%s\n' "$*"; }
warn() { printf 'aviso: %s\n' "$*" >&2; }
fail() { printf 'erro: %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '/^# Uma pessoa/,/^set -euo/p' "${BASH_SOURCE[0]}" | sed -e 's/^# \{0,1\}//' -e '/^set -euo/d'
}

fetch_remote() {
  if ! git -C "$ROOT" fetch --prune "$REMOTE" "$BRANCH" >/dev/null 2>&1; then
    fail "não consegui falar com $REMOTE. Confira a credencial do GitHub no WSL (git-credential do Windows) e a rede."
  fi
}

ahead_count() { git -C "$ROOT" rev-list --count "$REMOTE/$BRANCH..HEAD"; }
behind_count() { git -C "$ROOT" rev-list --count "HEAD..$REMOTE/$BRANCH"; }
dirty_count() { git -C "$ROOT" status --porcelain | wc -l | tr -d ' '; }
short_sha() { git -C "$ROOT" rev-parse --short "$1"; }

report_divergence() {
  say "commits só nesta máquina (não publicados):"
  git -C "$ROOT" log --oneline --no-decorate "$REMOTE/$BRANCH..HEAD" | sed 's/^/  /'
  say "commits só no origin (publicados em outra máquina):"
  git -C "$ROOT" log --oneline --no-decorate "HEAD..$REMOTE/$BRANCH" | sed 's/^/  /'
}

show_status() {
  fetch_remote
  local ahead behind dirty
  ahead="$(ahead_count)"
  behind="$(behind_count)"
  dirty="$(dirty_count)"
  say "branch .......... $BRANCH"
  say "publicado ....... $REMOTE/$BRANCH em $(short_sha "$REMOTE/$BRANCH")"
  say "esta máquina .... HEAD em $(short_sha HEAD)"
  say "à frente ........ $ahead commit(s) local(is) não publicado(s)"
  say "atrás ........... $behind commit(s) publicados por outra máquina"
  say "não commitado ... $dirty arquivo(s)"
  if [ "$ahead" -gt 0 ] || [ "$behind" -gt 0 ]; then
    say ""
    report_divergence
  fi
}

start_work() {
  local allow_unpublished=0
  [ "${1:-}" = "--allow-unpublished" ] && allow_unpublished=1
  fetch_remote
  local ahead behind dirty
  ahead="$(ahead_count)"
  behind="$(behind_count)"
  dirty="$(dirty_count)"
  if [ "$ahead" -gt 0 ] && [ "$behind" -gt 0 ]; then
    warn "as duas máquinas têm commits: vou rebasear o trabalho local no que já está publicado."
    report_divergence
    git -C "$ROOT" rebase --autostash "$REMOTE/$BRANCH"
    ahead="$(ahead_count)"
    behind="$(behind_count)"
  fi
  if [ "$ahead" -gt 0 ]; then
    warn "esta máquina tem $ahead commit(s) não publicado(s) — publique antes de começar algo novo:"
    git -C "$ROOT" log --oneline --no-decorate "$REMOTE/$BRANCH..HEAD" | sed 's/^/  /'
    if [ "$allow_unpublished" -eq 0 ]; then
      fail "rode ./scripts/dev/sync.sh finish (ou publish) e comece de novo. Para ignorar: --allow-unpublished."
    fi
  fi
  if [ "$behind" -gt 0 ]; then
    say "atualizando com $behind commit(s) de outra máquina…"
    git -C "$ROOT" merge --ff-only "$REMOTE/$BRANCH"
  fi
  [ "$dirty" -eq 0 ] || warn "$dirty arquivo(s) não commitado(s) no checkout — confira se são seus antes de editar."
  say "pronto para trabalhar: HEAD em $(short_sha HEAD) (igual a $REMOTE/$BRANCH)"
  say "lembrete: comece pelo TASKS.md do workspace e pela spec em docs/specs/."
}

publish() {
  fetch_remote
  local behind
  behind="$(behind_count)"
  if [ "$behind" -gt 0 ]; then
    if [ "$(ahead_count)" -gt 0 ]; then
      warn "origin avançou; rebaseando o trabalho local antes de publicar."
      git -C "$ROOT" rebase --autostash "$REMOTE/$BRANCH"
    else
      git -C "$ROOT" merge --ff-only "$REMOTE/$BRANCH"
    fi
  fi
  git -C "$ROOT" push "$REMOTE" "$BRANCH"
  say "publicado: $(short_sha "$REMOTE/$BRANCH")"
}

finish_work() {
  local run_checks=1 allow_dirty=0 run_scan=1
  for arg in "$@"; do
    case "$arg" in
      --no-checks) run_checks=0 ;;
      --allow-dirty) allow_dirty=1 ;;
      --no-scan) run_scan=0 ;;
    esac
  done
  fetch_remote
  if [ "$(dirty_count)" -gt 0 ]; then
    warn "há arquivos não commitados nesta máquina:"
    git -C "$ROOT" status --short | sed 's/^/  /'
    if [ "$allow_dirty" -eq 0 ]; then
      fail "commite o que faz sentido (ou descarte o que não é seu) antes de fechar a máquina."
    fi
  fi
  if [ "$(behind_count)" -gt 0 ]; then
    if [ "$(ahead_count)" -gt 0 ]; then
      warn "origin avançou; rebaseando o trabalho local."
      git -C "$ROOT" rebase --autostash "$REMOTE/$BRANCH"
    else
      git -C "$ROOT" merge --ff-only "$REMOTE/$BRANCH"
    fi
  fi
  if [ "$(ahead_count)" -eq 0 ]; then
    say "nada local para publicar; esta máquina está igual a $REMOTE/$BRANCH."
    return
  fi
  if [ "$run_checks" -eq 1 ]; then
    say "rodando o portão completo antes de publicar…"
    bash "$ROOT/scripts/dev/checks.sh" all
  fi
  if [ "$run_scan" -eq 1 ]; then
    say "varrendo segredo antes de publicar…"
    bash "$ROOT/scripts/dev/secret-scan.sh" || fail "scan de segredo reprovou; corrija antes de publicar (escapes: --no-scan)."
  fi
  git -C "$ROOT" push "$REMOTE" "$BRANCH"
  say "publicado: $(short_sha "$REMOTE/$BRANCH") — pode trocar de máquina."
  say "próximo passo (quando a mudança é de app): deploy pelo wrapper privado, com smoke público."
}

case "${1:-status}" in
  status) show_status ;;
  start)
    shift || true
    start_work "${1:-}"
    ;;
  finish)
    shift || true
    finish_work "$@"
    ;;
  publish) publish ;;
  help | -h | --help)
    usage
    ;;
  *)
    usage
    exit 1
    ;;
esac
