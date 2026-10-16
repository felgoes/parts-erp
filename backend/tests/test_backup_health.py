"""Regras do backup da P16: atraso, motivo em português e retenção das cópias locais."""

import os

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import InvalidToken

from app.models import ErpSettings
from app.services import backup_health as health

CONNECTED = "token-cifrado"


def _set_age(path: Path, moment: datetime) -> None:
    stamp = moment.timestamp()
    os.utime(path, (stamp, stamp))


def _settings(**overrides) -> ErpSettings:
    base = {
        "backup_enabled": True,
        "backup_frequency": "daily",
        "backup_time": "02:00",
        "backup_retention_days": 30,
        "encrypted_drive_refresh_token": CONNECTED,
    }
    base.update(overrides)
    return ErpSettings(**base)


def test_daily_backup_is_late_after_36_hours_without_success():
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)

    assert health.is_late(_settings(backup_last_success_at=now - timedelta(hours=35)), now) is False
    assert health.is_late(_settings(backup_last_success_at=now - timedelta(hours=37)), now) is True


def test_weekly_backup_is_late_after_eight_days():
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    recent = _settings(
        backup_frequency="weekly", backup_last_success_at=now - timedelta(days=7, hours=20)
    )
    old = _settings(
        backup_frequency="weekly", backup_last_success_at=now - timedelta(days=8, hours=1)
    )

    assert health.is_late(recent, now) is False
    assert health.is_late(old, now) is True


def test_late_state_does_not_depend_on_the_last_recorded_status():
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    settings = _settings(
        backup_last_status="success",
        backup_last_success_at=now - timedelta(days=2),
    )

    assert health.backup_state(settings, now) == "late"


def test_linha_anterior_a_p16_usa_backup_last_at_como_ultimo_sucesso():
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    legado = _settings(
        backup_last_status="failed",
        backup_last_at=now - timedelta(days=2),
        backup_last_error="400 Bad Request",
    )

    assert health.last_success_at(legado) == now - timedelta(days=2)
    assert health.backup_state(legado, now) == "late"


def test_depois_da_p16_a_ultima_tentativa_nao_vira_ultimo_sucesso():
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    settings = _settings(
        backup_last_status="failed",
        backup_last_at=now - timedelta(hours=1),
        backup_last_attempt_at=now - timedelta(hours=1),
    )

    assert health.last_success_at(settings) is None
    assert health.backup_state(settings, now) == "failed"


def test_state_reports_failure_after_the_last_success():
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    failed = _settings(
        backup_last_status="failed",
        backup_last_success_at=now - timedelta(hours=10),
        backup_last_attempt_at=now - timedelta(hours=9),
    )
    recovered = _settings(
        backup_last_status="success",
        backup_last_success_at=now - timedelta(hours=1),
        backup_last_attempt_at=now - timedelta(hours=1),
    )

    assert health.backup_state(failed, now) == "failed"
    assert health.backup_state(recovered, now) == "ok"


def test_state_without_connection_or_permission():
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)

    assert health.backup_state(_settings(encrypted_drive_refresh_token=None), now) == (
        "setup_required"
    )
    assert health.backup_state(_settings(backup_enabled=False), now) == "disabled"
    assert health.backup_state(_settings(), now) == "pending"


def test_next_run_is_the_next_local_target_time():
    settings = _settings()

    # 05:00 UTC é 02:00 em São Paulo: o próximo previsto é o dia seguinte.
    assert health.next_run_at(settings, datetime(2026, 10, 16, 5, 0, tzinfo=UTC)) == datetime(
        2026, 10, 17, 5, 0, tzinfo=UTC
    )
    # 04:00 UTC é 01:00 em São Paulo: ainda dá hoje.
    assert health.next_run_at(settings, datetime(2026, 10, 16, 4, 0, tzinfo=UTC)) == datetime(
        2026, 10, 16, 5, 0, tzinfo=UTC
    )
    assert health.next_run_at(_settings(backup_enabled=False)) is None


def test_next_weekly_run_counts_seven_days_from_the_last_success():
    settings = _settings(
        backup_frequency="weekly",
        backup_last_success_at=datetime(2026, 10, 12, 5, 0, tzinfo=UTC),
    )

    assert health.next_run_at(settings, datetime(2026, 10, 16, 12, 0, tzinfo=UTC)) == datetime(
        2026, 10, 19, 5, 0, tzinfo=UTC
    )


def test_cleanup_removes_expired_copies_and_keeps_the_fresh_ones(tmp_path: Path):
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    settings = _settings(backup_retention_days=7)
    expired = [
        "parts-erp-backup-20261001-020000.db",
        "code-20261001-020000.tar.gz",
        "db-20261001-020000.sqlite",
        "parts-erp-pre-ef0ec53-20261001.tar.gz",
    ]
    fresh = ["parts-erp-backup-20261016-020000.db", "code-20261016-020000.tar.gz"]
    old_folder = tmp_path / "frontend-pre-20261001-020000"
    for name in expired + fresh:
        (tmp_path / name).write_bytes(b"copia")
    old_folder.mkdir()
    (old_folder / "index.html").write_text("antigo", encoding="utf-8")
    for name in expired:
        _set_age(tmp_path / name, now - timedelta(days=40))
    _set_age(old_folder, now - timedelta(days=40))
    for name in fresh:
        _set_age(tmp_path / name, now - timedelta(days=1))

    removed = health.cleanup_local_backups(settings, tmp_path, now)

    assert sorted(removed) == sorted(expired + [old_folder.name])
    assert not old_folder.exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(fresh)


def test_cleanup_ignores_files_outside_the_backup_patterns(tmp_path: Path):
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    settings = _settings(backup_retention_days=1)
    keep = tmp_path / "parts-erp.db"
    keep.write_bytes(b"banco em uso")
    _set_age(keep, now - timedelta(days=90))

    assert health.cleanup_local_backups(settings, tmp_path, now) == []
    assert keep.exists()


def test_invalid_grant_has_a_clear_portuguese_message():
    request = httpx.Request("POST", "https://oauth2.googleapis.com/token")
    response = httpx.Response(
        400, json={"error": "invalid_grant", "error_description": "Token has been expired"}, request=request
    )
    error = httpx.HTTPStatusError("bad request", request=request, response=response)

    code, message = health.describe_drive_error(error)

    assert code == "invalid_grant"
    assert "expirou ou foi revogada" in message
    assert "Reconecte" in message


def test_network_failure_says_the_local_copy_was_kept():
    request = httpx.Request("POST", "https://www.googleapis.com/upload/drive/v3/files")
    error = httpx.ConnectError("sem rota", request=request)

    code, message = health.describe_drive_error(error)

    assert code == "network"
    assert "cópia local do dia foi mantida" in message


def test_recusada_credencial_do_aplicativo_aponta_para_client_id_e_segredo():
    request = httpx.Request("POST", "https://oauth2.googleapis.com/token")
    response = httpx.Response(
        401, json={"error": "invalid_client", "error_description": "Unauthorized"}, request=request
    )
    error = httpx.HTTPStatusError("unauthorized", request=request, response=response)

    code, message = health.describe_drive_error(error)

    assert code == "invalid_client"
    assert "Client ID" in message
    assert "segredo OAuth" in message


def test_credencial_guardada_ilegivel_pede_reconexao():
    code, message = health.describe_drive_error(InvalidToken())

    assert code == "credencial_ilegivel"
    assert "Reconecte a conta" in message


def test_retention_never_exceeds_the_configured_ceiling():
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)

    assert health.retention_cutoff(_settings(backup_retention_days=0), now) == now - timedelta(
        days=1
    )
    assert health.retention_cutoff(_settings(backup_retention_days=90), now) == now - timedelta(
        days=health.DEFAULT_RETENTION_DAYS
    )
