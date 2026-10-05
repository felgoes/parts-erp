"""procurement negotiation, purchase and receiving workflow"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "30_purchase_workflow"
down_revision: str | None = "29_ml_invoice_dates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE movementtype ADD VALUE IF NOT EXISTS 'purchase_received'")
    op.create_table(
        "purchase_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("number", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("selected_quote_id", sa.String(36)),
        sa.Column("needed_by", sa.DateTime(timezone=True)),
        sa.Column("ordered_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_purchase_cases_number", "purchase_cases", ["number"], unique=True)
    op.create_index("ix_purchase_cases_status", "purchase_cases", ["status"])
    op.create_table(
        "purchase_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "purchase_id",
            sa.String(36),
            sa.ForeignKey("purchase_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id")),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("received_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=False),
    )
    op.create_index("ix_purchase_items_purchase_id", "purchase_items", ["purchase_id"])
    op.create_table(
        "purchase_quotes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "purchase_id",
            sa.String(36),
            sa.ForeignKey("purchase_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("supplier_name", sa.String(200), nullable=False),
        sa.Column("supplier_contact", sa.String(200)),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("delivery_days", sa.Integer()),
        sa.Column("payment_terms", sa.String(200)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_purchase_quotes_purchase_id", "purchase_quotes", ["purchase_id"])
    op.create_table(
        "purchase_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "purchase_id",
            sa.String(36),
            sa.ForeignKey("purchase_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("detail", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_purchase_events_purchase_created", "purchase_events", ["purchase_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_purchase_events_purchase_created", table_name="purchase_events")
    op.drop_table("purchase_events")
    op.drop_index("ix_purchase_quotes_purchase_id", table_name="purchase_quotes")
    op.drop_table("purchase_quotes")
    op.drop_index("ix_purchase_items_purchase_id", table_name="purchase_items")
    op.drop_table("purchase_items")
    op.drop_index("ix_purchase_cases_status", table_name="purchase_cases")
    op.drop_index("ix_purchase_cases_number", table_name="purchase_cases")
    op.drop_table("purchase_cases")
