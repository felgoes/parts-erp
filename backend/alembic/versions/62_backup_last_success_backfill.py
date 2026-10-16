"""preserva o último sucesso das linhas anteriores à P16

Revision ID: 62_backup_last_success_backfill
Revises: 61_backup_health
"""

from collections.abc import Sequence

from alembic import op

revision: str = "62_backup_last_success_backfill"
down_revision: str | None = "61_backup_health"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Antes da P16, `backup_last_at` só era gravado quando o backup concluía, e
    # `backup_last_attempt_at` ainda não existia. Sem esta cópia, a primeira falha depois
    # da entrega apagaria da tela a informação de quando houve o último backup bom —
    # justamente o dado que denuncia o atraso.
    op.execute(
        "UPDATE erp_settings SET backup_last_success_at = backup_last_at "
        "WHERE backup_last_success_at IS NULL AND backup_last_attempt_at IS NULL "
        "AND backup_last_at IS NOT NULL"
    )


def downgrade() -> None:
    # A cópia é informativa; nada a desfazer sem risco de apagar histórico legítimo.
    pass
