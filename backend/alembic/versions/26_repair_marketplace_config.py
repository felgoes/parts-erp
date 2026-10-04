"""repair marketplace automation config columns when prior migration was partial

Revision ID: 26_repair_ml_config
Revises: 25_shopee_source
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "26_repair_ml_config"
down_revision: str | None = "25_shopee_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("marketplace_config")}
    if "auto_issue_invoice" not in columns:
        op.add_column("marketplace_config", sa.Column("auto_issue_invoice", sa.Boolean(), nullable=False, server_default=sa.true()))
    if "auto_download_label" not in columns:
        op.add_column("marketplace_config", sa.Column("auto_download_label", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("marketplace_config")}
    for name in ("auto_download_label", "auto_issue_invoice"):
        if name in columns:
            op.drop_column("marketplace_config", name)
