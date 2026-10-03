"""marketplace document automation

Revision ID: 24_marketplace_auto
Revises: 23_telemetry
Create Date: 2026-10-03 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "24_marketplace_auto"
down_revision: str | None = "23_telemetry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "marketplace_config",
        sa.Column("auto_issue_invoice", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "marketplace_config",
        sa.Column("auto_download_label", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("marketplace_orders", sa.Column("shipment_id", sa.String(80)))
    op.add_column("marketplace_orders", sa.Column("shipping_status", sa.String(60)))
    op.add_column(
        "marketplace_orders",
        sa.Column("fiscal_status", sa.String(30), nullable=False, server_default="pending"),
    )
    op.add_column("marketplace_orders", sa.Column("fiscal_error", sa.Text()))
    op.add_column("marketplace_orders", sa.Column("external_invoice_id", sa.String(80)))
    op.add_column(
        "marketplace_orders",
        sa.Column("label_status", sa.String(30), nullable=False, server_default="pending"),
    )
    op.add_column("marketplace_orders", sa.Column("label_error", sa.Text()))
    op.add_column(
        "marketplace_orders", sa.Column("automation_updated_at", sa.DateTime(timezone=True))
    )
    op.create_index("ix_marketplace_orders_shipment_id", "marketplace_orders", ["shipment_id"])
    op.create_index(
        "ix_marketplace_orders_external_invoice_id",
        "marketplace_orders",
        ["external_invoice_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_marketplace_orders_external_invoice_id", table_name="marketplace_orders")
    op.drop_index("ix_marketplace_orders_shipment_id", table_name="marketplace_orders")
    op.drop_column("marketplace_orders", "automation_updated_at")
    op.drop_column("marketplace_orders", "label_error")
    op.drop_column("marketplace_orders", "label_status")
    op.drop_column("marketplace_orders", "external_invoice_id")
    op.drop_column("marketplace_orders", "fiscal_error")
    op.drop_column("marketplace_orders", "fiscal_status")
    op.drop_column("marketplace_orders", "shipping_status")
    op.drop_column("marketplace_orders", "shipment_id")
    op.drop_column("marketplace_config", "auto_download_label")
    op.drop_column("marketplace_config", "auto_issue_invoice")
