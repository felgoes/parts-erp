"""recupera o último sucesso a partir dos avisos de backup já enviados

Revision ID: 63_backup_last_success_from_notices
Revises: 62_backup_last_success_backfill
"""

from collections.abc import Sequence

from alembic import op

revision: str = "63_backup_last_success_from_notices"
down_revision: str | None = "62_backup_last_success_backfill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Entre a P16 e esta migração, a primeira tentativa já sobrescreveu `backup_last_at`,
    # que era onde a data do último backup bom morava. O aviso "Backup concluído" foi
    # gravado a cada sucesso, então ele preserva essa data — sem ele a tela diria
    # "nenhum backup" para uma instalação que teve backup até a autorização expirar.
    op.execute(
        "UPDATE erp_settings SET backup_last_success_at = ("
        " SELECT MAX(created_at) FROM push_notifications WHERE dedupe_key LIKE 'backup:%'"
        ") WHERE backup_last_success_at IS NULL AND EXISTS ("
        " SELECT 1 FROM push_notifications WHERE dedupe_key LIKE 'backup:%'"
        ")"
    )


def downgrade() -> None:
    # A data recuperada é histórica e verdadeira; não há o que desfazer.
    pass
