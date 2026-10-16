"""Regras do backup automático: atraso, próxima execução, nova tentativa e retenção.

Separado de `google_drive_backup.py` para a decisão (pura e testável) ficar longe do acesso
ao Google Drive, e para os dois arquivos caberem no teto de leitura do projeto.
"""

from __future__ import annotations

import shutil
from datetime import UTC, date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:  # pragma: no cover - depende do tzdata instalado na máquina
    BACKUP_TIMEZONE = ZoneInfo("America/Sao_Paulo")
except ZoneInfoNotFoundError:  # Termux pode não ter o pacote tzdata
    BACKUP_TIMEZONE = timezone(timedelta(hours=-3), name="America/Sao_Paulo")

# Um backup diário que passou de 36 horas sem sucesso está atrasado; o semanal, de 8 dias.
DAILY_LATE_AFTER = timedelta(hours=36)
WEEKLY_LATE_AFTER = timedelta(days=8)
# Depois de falhar, o ERP tenta de novo em intervalo controlado e no máximo quatro vezes
# por janela — em vez das centenas de tentativas por dia que a autorização expirada gerava.
RETRY_INTERVAL = timedelta(minutes=30)
MAX_ATTEMPTS_PER_WINDOW = 4
DEFAULT_RETENTION_DAYS = 30
# Cópias locais sob a retenção: as do próprio backup e as geradas pelo deploy.
LOCAL_COPY_PATTERNS = (
    "parts-erp-backup-*.db",
    "code-*.tar.gz",
    "db-*.sqlite",
    "frontend-pre-*",
    "parts-erp-pre-*",
    "hardening-*",
)


def _as_utc(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        # O SQLite perde a marca de fuso; os horários de backup são gravados em UTC.
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def local_day(moment: datetime) -> date:
    return _as_utc(moment).astimezone(BACKUP_TIMEZONE).date()


def parse_backup_time(value: Any) -> time:
    try:
        hour, minute = (int(part) for part in str(value or "02:00").split(":", 1))
        return time(hour, minute)
    except (AttributeError, TypeError, ValueError):
        return time(2, 0)


def last_success_at(row: Any) -> datetime | None:
    explicit = _as_utc(getattr(row, "backup_last_success_at", None))
    if explicit is not None:
        return explicit
    # Registros anteriores à P16 gravavam `backup_last_at` apenas no sucesso — e nunca
    # preenchiam `backup_last_attempt_at`. Depois da P16, `backup_last_at` é a última
    # tentativa (que pode ter falhado), então o valor não serve mais como sucesso.
    if getattr(row, "backup_last_attempt_at", None) is None:
        return _as_utc(getattr(row, "backup_last_at", None))
    return None


def last_attempt_at(row: Any) -> datetime | None:
    return _as_utc(getattr(row, "backup_last_attempt_at", None)) or _as_utc(
        getattr(row, "backup_last_at", None)
    )


def late_after(row: Any) -> timedelta:
    if getattr(row, "backup_frequency", "daily") == "weekly":
        return WEEKLY_LATE_AFTER
    return DAILY_LATE_AFTER


def is_late(row: Any, now: datetime | None = None) -> bool:
    """Atraso pelo último sucesso, não pelo último registro de status."""
    moment = _as_utc(now or datetime.now(UTC))
    reference = last_success_at(row) or last_attempt_at(row)
    if reference is None:
        # Nunca houve sucesso nem tentativa: ainda não há o que cobrar.
        return False
    return moment - reference > late_after(row)


def has_pending_failure(row: Any) -> bool:
    if getattr(row, "backup_last_status", None) != "failed":
        return False
    attempt = last_attempt_at(row)
    success = last_success_at(row)
    return attempt is not None and (success is None or attempt > success)


def backup_state(row: Any, now: datetime | None = None) -> str:
    """Estado para a tela: setup_required, disabled, pending, failed, late ou ok."""
    connected = bool(getattr(row, "encrypted_drive_refresh_token", None))
    if not connected:
        return "setup_required"
    if not getattr(row, "backup_enabled", False):
        return "disabled"
    if is_late(row, now):
        return "late"
    if has_pending_failure(row):
        return "failed"
    if last_success_at(row) is None:
        return "pending"
    return "ok"


def next_run_at(row: Any, now: datetime | None = None) -> datetime | None:
    """Próximo horário previsto do backup, em UTC, ou None se o backup não estiver ligado."""
    if not getattr(row, "backup_enabled", False):
        return None
    weekly = getattr(row, "backup_frequency", "daily") == "weekly"
    moment = _as_utc(now or datetime.now(UTC))
    local_now = moment.astimezone(BACKUP_TIMEZONE)
    target = parse_backup_time(getattr(row, "backup_time", "02:00"))
    reference = last_success_at(row)
    if weekly and reference is not None:
        base = reference.astimezone(BACKUP_TIMEZONE).date()
    else:
        base = local_now.date()
    candidate = datetime.combine(base, target, tzinfo=BACKUP_TIMEZONE)
    step = timedelta(days=7 if weekly else 1)
    while candidate <= local_now:
        candidate += step
    return candidate.astimezone(UTC)


def attempts_in_window(row: Any, window: date) -> int:
    if getattr(row, "backup_attempts_date", None) != window.isoformat():
        return 0
    return max(0, int(getattr(row, "backup_attempts_today", 0) or 0))


def current_window_day(row: Any, now: datetime | None = None) -> date | None:
    """Dia local da janela já aberta (a partir do horário configurado), ou None."""
    local_now = _as_utc(now or datetime.now(UTC)).astimezone(BACKUP_TIMEZONE)
    if local_now.time() < parse_backup_time(getattr(row, "backup_time", "02:00")):
        return None
    return local_now.date()


def scheduled_backup_due(row: Any, now: datetime | None = None) -> bool:
    """Diz se o worker deve tentar o backup agora.

    A tentativa acontece na janela do dia configurado, uma vez por dia em caso de sucesso e,
    em caso de falha, no máximo `MAX_ATTEMPTS_PER_WINDOW` vezes respeitando `RETRY_INTERVAL`.
    """
    moment = _as_utc(now or datetime.now(UTC))
    window = current_window_day(row, moment)
    if window is None:
        return False
    success = last_success_at(row)
    if success is not None:
        elapsed_days = (window - success.astimezone(BACKUP_TIMEZONE).date()).days
        if getattr(row, "backup_frequency", "daily") == "weekly":
            if elapsed_days < 7:
                return False
        elif elapsed_days < 1:
            return False
    if attempts_in_window(row, window) >= MAX_ATTEMPTS_PER_WINDOW:
        return False
    attempt = last_attempt_at(row)
    if attempt is not None and attempt.astimezone(BACKUP_TIMEZONE).date() == window:
        if moment - attempt < RETRY_INTERVAL:
            return False
    return True


def retention_cutoff(row: Any, now: datetime | None = None) -> datetime:
    days = int(getattr(row, "backup_retention_days", DEFAULT_RETENTION_DAYS) or 0)
    days = max(1, min(days, DEFAULT_RETENTION_DAYS))
    return _as_utc(now or datetime.now(UTC)) - timedelta(days=days)


def local_backup_dir(row: Any = None) -> Path:
    from app.core.config import get_settings

    directory = str(getattr(row, "backup_local_dir", "") or "").strip()
    return Path(directory or get_settings().backup_dir).expanduser().resolve()


def cleanup_local_backups(
    row: Any, directory: Path | None = None, now: datetime | None = None
) -> list[str]:
    """Remove as cópias locais vencidas e devolve o nome do que saiu."""
    target_dir = directory or local_backup_dir(row)
    if not target_dir.is_dir():
        return []
    cutoff = retention_cutoff(row, now).timestamp()
    removed: list[str] = []
    for pattern in LOCAL_COPY_PATTERNS:
        for entry in sorted(target_dir.glob(pattern)):
            try:
                if entry.stat().st_mtime >= cutoff:
                    continue
                if entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
            except OSError:
                continue
            removed.append(entry.name)
    return removed


_QUOTA_CODES = {"storageQuotaExceeded", "quotaExceeded", "userRateLimitExceeded", "rateLimitExceeded"}


def describe_drive_error(exc: BaseException) -> tuple[str, str]:
    """Traduz a falha do provedor em código curto e mensagem em português."""
    import httpx
    from cryptography.fernet import InvalidToken

    if isinstance(exc, InvalidToken):
        return (
            "credencial_ilegivel",
            "A credencial guardada do Google Drive não pôde ser lida. "
            "Reconecte a conta em Configurações › Backups.",
        )
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        payload: dict[str, Any] = {}
        try:
            body = exc.response.json()
            if isinstance(body, dict):
                payload = body
        except ValueError:
            payload = {}
        provider_code = str(payload.get("error") or "").strip()
        if provider_code in {"invalid_grant", "invalid_request", "unauthorized_client"}:
            return (
                provider_code,
                "A autorização do Google Drive expirou ou foi revogada. "
                "Reconecte a conta em Configurações › Backups.",
            )
        if provider_code == "invalid_client":
            return (
                provider_code,
                "O Google recusou as credenciais do aplicativo. "
                "Confira o Client ID e o segredo OAuth em Configurações › Backups.",
            )
        if status in {401, 403}:
            return (
                provider_code or f"http_{status}",
                "O Google recusou o acesso ao Drive. Reconecte a conta para liberar o backup.",
            )
        if status == 429 or provider_code in _QUOTA_CODES:
            return (
                provider_code or "http_429",
                "O Google limitou as chamadas agora. O ERP tenta de novo no próximo intervalo.",
            )
        if status >= 500:
            return (
                provider_code or f"http_{status}",
                "O Google Drive está indisponível no momento; a cópia local do dia foi mantida.",
            )
        return (
            provider_code or f"http_{status}",
            f"O Google recusou a operação (HTTP {status}). "
            "Confira a configuração da conta em Configurações › Backups.",
        )
    if isinstance(exc, httpx.HTTPError):
        return (
            "network",
            "Não foi possível falar com o Google Drive (sem rede ou tempo esgotado); "
            "a cópia local do dia foi mantida.",
        )
    detail = str(exc).strip() or type(exc).__name__
    return ("erro", f"Falha ao executar o backup: {detail}"[:300])
