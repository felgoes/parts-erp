"""saúde do backup: último sucesso, última tentativa, motivo e controle de tentativas

Revision ID: 61_backup_health
Revises: 60_purchase_extra_fee
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "61_backup_health"
down_revision: str | None = "60_purchase_extra_fee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("erp_settings") as batch_op:
        batch_op.add_column(
            sa.Column("backup_last_success_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("backup_last_attempt_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("backup_last_error_code", sa.String(60), nullable=True))
        batch_op.add_column(
            sa.Column("backup_attempts_today", sa.Integer, nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("backup_attempts_date", sa.String(10), nullable=True))
    # Os registros anteriores à P16 só gravavam `backup_last_at` no sucesso.
    op.execute(
        "UPDATE erp_settings SET backup_last_success_at = backup_last_at "
        "WHERE backup_last_status = 'success' AND backup_last_at IS NOT NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("erp_settings") as batch_op:
        batch_op.drop_column("backup_attempts_date")
        batch_op.drop_column("backup_attempts_today")
        batch_op.drop_column("backup_last_error_code")
        batch_op.drop_column("backup_last_attempt_at")
        batch_op.drop_column("backup_last_success_at")
