#!/usr/bin/env bash
# HML local do Parts ERP em um comando: API, ERP e login de QA no WSL.
#
#   ./scripts/hml-local.sh start      (ou subir)     sobe tudo e mostra os endereços
#   ./scripts/hml-local.sh stop       (ou parar)     para tudo o que este script iniciou
#   ./scripts/hml-local.sh restart    (ou reiniciar) para e sobe de novo
#   ./scripts/hml-local.sh status                    mostra o que está ativo e as portas
#   ./scripts/hml-local.sh logs [serviço|all]        acompanha os logs
#
# Serviços: backend (API em 127.0.0.1:8000), frontend (ERP em 127.0.0.1:4200) e
# qa-login (helper local que preenche o formulário de login de QA).
# Serviços já ativos em outra sessão são adotados, não reiniciados; stop encerra
# apenas os processos que este script iniciou. Nenhuma credencial é impressa.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
VENV_PY="$BACKEND_DIR/.venv/bin/python"
RUNTIME_DIR="${TMPDIR:-/tmp}/parts-erp-hml/$(printf '%s' "$ROOT" | md5sum | cut -c1-8)"
API_PORT="${PARTS_ERP_API_PORT:-8000}"
WEB_PORT="${PARTS_ERP_WEB_PORT:-4200}"
# Fixado pelo helper e pelo proxy de desenvolvimento em frontend/proxy.conf.json.
QA_PORT=8765

SERVICES=(backend frontend qa-login)

say() { printf '%s\n' "$*"; }
ok() { printf '  ok      %s\n' "$*"; }
info() { printf '  --      %s\n' "$*"; }
warn() { printf '  aviso   %s\n' "$*" >&2; }
fail() { printf 'erro: %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '/^# HML local/,/^set -euo/p' "${BASH_SOURCE[0]}" | sed -e 's/^# \{0,1\}//' -e '/^set -euo/d'
}

pid_file() { printf '%s/%s.pid' "$RUNTIME_DIR" "$1"; }
log_file() { printf '%s/%s.log' "$RUNTIME_DIR" "$1"; }

port_for() {
  case "$1" in
    backend) printf '%s' "$API_PORT" ;;
    frontend) printf '%s' "$WEB_PORT" ;;
    qa-login) printf '%s' "$QA_PORT" ;;
    *) fail "serviço desconhecido: $1" ;;
  esac
}

marker_for() {
  case "$1" in
    backend) printf 'uvicorn app.main:app' ;;
    frontend) printf 'npm start' ;;
    qa-login) printf 'qa-login-helper.py' ;;
    *) fail "serviço desconhecido: $1" ;;
  esac
}

health_url_for() {
  case "$1" in
    backend) printf 'http://127.0.0.1:%s/health' "$API_PORT" ;;
    frontend) printf 'http://127.0.0.1:%s/' "$WEB_PORT" ;;
    qa-login) printf 'http://127.0.0.1:%s/__qa-login' "$QA_PORT" ;;
    *) fail "serviço desconhecido: $1" ;;
  esac
}

label_for() {
  case "$1" in
    backend) printf 'API em http://localhost:%s/docs' "$API_PORT" ;;
    frontend) printf 'ERP em http://localhost:%s' "$WEB_PORT" ;;
    qa-login) printf 'Login de QA em http://localhost:%s/__qa-login' "$WEB_PORT" ;;
    *) fail "serviço desconhecido: $1" ;;
  esac
}

# PID sob o qual este script iniciou o serviço (falha quando não é nosso).
own_pid() {
  local name="$1" file pid
  file="$(pid_file "$name")"
  [ -f "$file" ] || return 1
  pid="$(cat "$file" 2>/dev/null || true)"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  ps -p "$pid" -o args= 2>/dev/null | grep -q -- "$(marker_for "$name")" || return 1
  printf '%s' "$pid"
}

# PID de quem estiver atendendo na porta, desta sessão ou de outra.
port_pid() {
  local port="$1"
  ss -ltnp 2>/dev/null | grep -F ":$port " | grep -o 'pid=[0-9]\+' | head -1 | cut -d= -f2 || true
}

port_busy() {
  [ -n "$(port_pid "$1")" ] && return 0
  ss -ltn 2>/dev/null | grep -q ":$1 " && return 0
  return 1
}

http_ok() { curl -fsS -o /dev/null --max-time 3 "$1" >/dev/null 2>&1; }

wait_http() {
  local url="$1" label="$2" tries="${3:-60}" i
  for ((i = 0; i < tries; i++)); do
    if http_ok "$url"; then ok "$label"; return 0; fi
    sleep 0.5
  done
  return 1
}

start_service() {
  local name="$1"
  shift
  local pid file log port url
  if pid="$(own_pid "$name")"; then
    info "$name já estava ativo nesta sessão (pid $pid)"
    return 0
  fi
  port="$(port_for "$name")"
  url="$(health_url_for "$name")"
  if port_busy "$port"; then
    if http_ok "$url"; then
      info "$name já está ativo em outro processo (pid $(port_pid "$port") na porta $port); preservado"
      return 0
    fi
    fail "a porta $port está ocupada pelo pid $(port_pid "$port") e não responde em $url. Libere a porta ou use PARTS_ERP_*_PORT."
  fi
  mkdir -p "$RUNTIME_DIR"
  file="$(pid_file "$name")"
  log="$(log_file "$name")"
  rm -f "$file"
  setsid nohup bash -c 'target="$1"; shift; printf "%s" "$$" > "$target"; exec "$@"' _ "$file" "$@" >"$log" 2>&1 &
  for _ in $(seq 1 40); do
    sleep 0.25
    if pid="$(own_pid "$name")"; then
      ok "$name iniciado (pid $pid, log $log)"
      return 0
    fi
  done
  tail -n 20 "$log" >&2 || true
  pid="$(cat "$file" 2>/dev/null || true)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  fi
  rm -f "$file"
  fail "$name não iniciou; veja $log"
}

stop_service() {
  local name="$1" pid port
  port="$(port_for "$name")"
  if ! pid="$(own_pid "$name")"; then
    rm -f "$(pid_file "$name")"
    if port_busy "$port"; then
      info "$name ativo em outro processo (pid $(port_pid "$port")); preservado"
    else
      info "$name não está ativo"
    fi
    return 0
  fi
  kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  for _ in $(seq 1 40); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.25
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
    sleep 0.5
  fi
  rm -f "$(pid_file "$name")"
  ok "$name parado"
}

ensure_prerequisites() {
  [ "$(uname -s)" = "Linux" ] || fail "rode este script no WSL Ubuntu, não no Windows."
  [ -x "$VENV_PY" ] || fail "ambiente Python ausente em backend/.venv. Rode ./scripts/setup-local.sh."
  [ -d "$FRONTEND_DIR/node_modules" ] || fail "dependências do frontend ausentes. Rode ./scripts/setup-local.sh."
  command -v curl >/dev/null || fail "curl não encontrado."
  if ! command -v npm >/dev/null 2>&1 && [ -s "$HOME/.nvm/nvm.sh" ]; then
    # shellcheck disable=SC1091
    . "$HOME/.nvm/nvm.sh" >/dev/null 2>&1 || true
  fi
  command -v npm >/dev/null 2>&1 || fail "npm não encontrado. Instale o Node via nvm (veja docs/development-setup.md)."
}

ensure_backend_env() {
  local env_file="$BACKEND_DIR/.env"
  [ -f "$env_file" ] && return 0
  if [ -f "$ROOT/.env.qa.local" ]; then
    cp "$ROOT/.env.qa.local" "$env_file"
    chmod 600 "$env_file"
    info "criei backend/.env a partir de .env.qa.local (arquivo ignorado pelo Git)"
  else
    fail "backend/.env ausente e .env.qa.local não encontrado. Crie backend/.env antes de subir o HML."
  fi
}

ensure_migrations() {
  mkdir -p "$RUNTIME_DIR"
  (cd "$BACKEND_DIR" && "$VENV_PY" -m alembic upgrade head >"$RUNTIME_DIR/migrations.log" 2>&1) ||
    fail "migrações falharam; veja $RUNTIME_DIR/migrations.log"
  ok "banco de QA atualizado (alembic upgrade head)"
}

check_redis() {
  if command -v redis-cli >/dev/null 2>&1 && redis-cli -h 127.0.0.1 -p 6379 ping >/dev/null 2>&1; then
    ok "redis respondendo em 127.0.0.1:6379"
  else
    warn "redis não respondeu em 127.0.0.1:6379; a fila de notificações pode não processar."
  fi
}

start_all() {
  ensure_prerequisites
  say "Preparando o HML local em $ROOT"
  ensure_backend_env
  ensure_migrations
  check_redis

  say "Subindo serviços"
  start_service backend env -C "$BACKEND_DIR" "$VENV_PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT"
  start_service frontend env -C "$FRONTEND_DIR" npm start -- --port "$WEB_PORT"
  start_service qa-login python3 "$ROOT/scripts/qa-login-helper.py"

  say "Aguardando responder"
  local name
  for name in "${SERVICES[@]}"; do
    wait_http "$(health_url_for "$name")" "$(label_for "$name")" 180 || fail "$name não respondeu em $(health_url_for "$name")"
  done

  say ""
  say "HML local pronto:"
  say "  ERP ............ http://localhost:$WEB_PORT"
  say "  Login de QA .... http://localhost:$WEB_PORT/__qa-login"
  say "  API/OpenAPI .... http://localhost:$API_PORT/docs"
  say "  Logs ........... ./scripts/hml-local.sh logs"
  say "  Parar .......... ./scripts/hml-local.sh stop   (encerra só o que este script iniciou)"
}

stop_all() {
  say "Parando o HML local"
  local name
  for name in "${SERVICES[@]}"; do stop_service "$name"; done
}

status_all() {
  local name pid port
  for name in "${SERVICES[@]}"; do
    port="$(port_for "$name")"
    if pid="$(own_pid "$name")"; then
      printf '  %-9s ativo nesta sessão (pid %s, porta %s)\n' "$name" "$pid" "$port"
    elif port_busy "$port"; then
      printf '  %-9s ativo em outro processo (pid %s, porta %s)\n' "$name" "$(port_pid "$port")" "$port"
    else
      printf '  %-9s parado (porta %s livre)\n' "$name" "$port"
    fi
  done
}

logs_all() {
  local target="${1:-all}" name files=() existing=() f
  if [ "$target" = "all" ]; then
    for name in "${SERVICES[@]}"; do files+=("$(log_file "$name")"); done
  else
    marker_for "$target" >/dev/null
    files=("$(log_file "$target")")
  fi
  for f in "${files[@]}"; do [ -f "$f" ] && existing+=("$f"); done
  [ "${#existing[@]}" -gt 0 ] || fail "sem logs em $RUNTIME_DIR (os serviços podem ter sido iniciados por outra sessão)."
  tail -n 40 -f "${existing[@]}"
}

command="${1:-start}"
case "$command" in
  start | subir) start_all ;;
  stop | parar) stop_all ;;
  restart | reiniciar)
    stop_all
    start_all
    ;;
  status) status_all ;;
  logs)
    shift || true
    logs_all "${1:-all}"
    ;;
  help | -h | --help) usage ;;
  *)
    usage
    exit 1
    ;;
esac
