"""add marketplace order document automation fields

Revision ID: 24_marketplace_auto
Revises: 23_telemetry
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "24_marketplace_auto"
down_revision: str | None = "23_telemetry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("marketplace_config", sa.Column("auto_issue_invoice", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("marketplace_config", sa.Column("auto_download_label", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("marketplace_orders", sa.Column("shipment_id", sa.String(length=80), nullable=True))
    op.add_column("marketplace_orders", sa.Column("shipping_status", sa.String(length=60), nullable=True))
    op.add_column("marketplace_orders", sa.Column("fiscal_status", sa.String(length=30), nullable=False, server_default="pending"))
    op.add_column("marketplace_orders", sa.Column("fiscal_error", sa.Text(), nullable=True))
    op.add_column("marketplace_orders", sa.Column("external_invoice_id", sa.String(length=80), nullable=True))
    op.add_column("marketplace_orders", sa.Column("label_status", sa.String(length=30), nullable=False, server_default="pending"))
    op.add_column("marketplace_orders", sa.Column("label_error", sa.Text(), nullable=True))
    op.add_column("marketplace_orders", sa.Column("automation_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_marketplace_orders_shipment_id", "marketplace_orders", ["shipment_id"])
    op.create_index("ix_marketplace_orders_external_invoice_id", "marketplace_orders", ["external_invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_marketplace_orders_external_invoice_id", table_name="marketplace_orders")
    op.drop_index("ix_marketplace_orders_shipment_id", table_name="marketplace_orders")
    for name in ("automation_updated_at", "label_error", "label_status", "external_invoice_id", "fiscal_error", "fiscal_status", "shipping_status", "shipment_id"):
        op.drop_column("marketplace_orders", name)
    op.drop_column("marketplace_config", "auto_download_label")
    op.drop_column("marketplace_config", "auto_issue_invoice")
