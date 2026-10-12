"""Limite de tentativas de login, com contadores em memória.

Duas travas independentes, nenhuma delas bloqueando conta:

- **origem (IP)**: passou do limite de falhas na janela, a próxima tentativa daquele
  endereço responde 429 até a janela expirar sozinha.
- **conta (e-mail)**: falhas acumuladas só acrescentam atraso progressivo antes da
  verificação da senha; a senha certa continua entrando.

Os contadores vivem no processo da API (um uvicorn) por decisão de produto: se o Redis
cair, o login continua funcionando em vez de derrubar todo mundo. Reiniciar a API zera os
contadores — aceitável porque a janela é de 5 minutos.
"""

from collections import defaultdict, deque
from threading import Lock
from time import monotonic, sleep
from typing import Any

WINDOW_SECONDS = 300
IP_FAILURE_LIMIT = 10
DELAY_STEPS: tuple[float, ...] = (0.5, 1.0, 2.0)
DELAY_CAP_SECONDS = 3.0
_TRACKED_KEYS_LIMIT = 4096

# Referência de módulo: os testes substituem a espera por uma função sem dormir.
_sleep = sleep

_email_failures: dict[str, deque[float]] = defaultdict(deque)
_ip_failures: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def _prune(window: deque[float], now: float) -> None:
    while window and window[0] <= now - WINDOW_SECONDS:
        window.popleft()


def _drop_saturated(bucket: dict[str, deque[float]]) -> None:
    """Impede crescimento sem limite quando muitas origens tentam de uma vez."""
    if len(bucket) <= _TRACKED_KEYS_LIMIT:
        return
    for key in [key for key, window in bucket.items() if not window]:
        bucket.pop(key, None)
    while len(bucket) > _TRACKED_KEYS_LIMIT:
        oldest = min(bucket, key=lambda key: bucket[key][-1] if bucket[key] else 0.0)
        bucket.pop(oldest, None)


def _seconds_until_below(window: deque[float], now: float, keep: int) -> float:
    """Tempo até a janela guardar menos que `keep` falhas (0 = já está abaixo).

    Quando há exatamente `keep` falhas, basta a mais antiga expirar; cada falha além disso
    exige que a seguinte também expire.
    """
    if len(window) < keep:
        return 0.0
    index = len(window) - keep
    return max(0.0, (window[index] + WINDOW_SECONDS) - now)


def register_failure(email: str, ip: str) -> None:
    """Conta a falha nas duas chaves; só falhas chamam esta função."""
    now = monotonic()
    with _lock:
        for bucket, key in ((_email_failures, email), (_ip_failures, ip)):
            window = bucket[key]
            _prune(window, now)
            window.append(now)
        _drop_saturated(_email_failures)
        _drop_saturated(_ip_failures)


def clear_email(email: str) -> None:
    """Sucesso zera o contador da conta; a origem não é perdoada por um acerto alheio."""
    with _lock:
        _email_failures.pop(email, None)


def block_seconds_left(ip: str) -> float:
    """Segundos restantes de bloqueio da origem, ou 0 quando ela pode tentar."""
    now = monotonic()
    with _lock:
        window = _ip_failures.get(ip)
        if not window:
            return 0.0
        _prune(window, now)
        return _seconds_until_below(window, now, IP_FAILURE_LIMIT)


def delay_seconds(email: str) -> float:
    """Atraso a aplicar antes de verificar a senha, conforme as falhas da conta."""
    now = monotonic()
    with _lock:
        window = _email_failures.get(email)
        if not window:
            return 0.0
        _prune(window, now)
        failures = len(window)
    if not failures:
        return 0.0
    if failures <= len(DELAY_STEPS):
        return DELAY_STEPS[failures - 1]
    return DELAY_CAP_SECONDS


def pause_for(email: str) -> None:
    """Aplica o atraso progressivo da conta (não faz nada quando ela está limpa)."""
    seconds = delay_seconds(email)
    if seconds:
        _sleep(seconds)


def reset(*, email: str | None = None, ip: str | None = None) -> None:
    """Liberação administrativa: limpa a conta, a origem ou as duas."""
    with _lock:
        if email is not None:
            _email_failures.pop(email, None)
        if ip is not None:
            _ip_failures.pop(ip, None)


def clear_all() -> None:
    """Usado pelos testes para começar de um estado limpo."""
    with _lock:
        _email_failures.clear()
        _ip_failures.clear()


def snapshot() -> dict[str, Any]:
    """Estado atual para a tela de administração: o que está barrado e o que está atrasado."""
    now = monotonic()
    blocked: list[dict[str, Any]] = []
    delayed: list[dict[str, Any]] = []
    with _lock:
        for ip, window in _ip_failures.items():
            _prune(window, now)
            if not window:
                continue
            left = _seconds_until_below(window, now, IP_FAILURE_LIMIT)
            if left > 0:
                blocked.append(
                    {"ip": ip, "failures": len(window), "seconds_left": int(left + 0.999)}
                )
        for email, window in _email_failures.items():
            _prune(window, now)
            if not window:
                continue
            failures = len(window)
            step = DELAY_STEPS[failures - 1] if failures <= len(DELAY_STEPS) else DELAY_CAP_SECONDS
            left = max(0.0, (window[-1] + WINDOW_SECONDS) - now)
            delayed.append(
                {
                    "email": email,
                    "failures": failures,
                    "delay_seconds": step,
                    "seconds_left": int(left + 0.999),
                }
            )
        for bucket in (_email_failures, _ip_failures):
            for key in [key for key, window in bucket.items() if not window]:
                bucket.pop(key, None)
    blocked.sort(key=lambda entry: entry["seconds_left"], reverse=True)
    delayed.sort(key=lambda entry: entry["failures"], reverse=True)
    return {
        "window_seconds": WINDOW_SECONDS,
        "ip_failure_limit": IP_FAILURE_LIMIT,
        "delay_cap_seconds": DELAY_CAP_SECONDS,
        "blocked_origins": blocked,
        "delayed_accounts": delayed,
    }
