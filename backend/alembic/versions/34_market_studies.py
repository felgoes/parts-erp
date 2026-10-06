"""market research studies and pluggable AI connector"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "34_market_studies"
down_revision: str | None = "33_after_sale_returns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_study_connector_config",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("base_url", sa.String(500)),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("encrypted_api_key", sa.Text()),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "market_studies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("search_term", sa.String(200), nullable=False),
        sa.Column("sku", sa.String(80)),
        sa.Column("category_id", sa.String(40)),
        sa.Column("landed_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("target_margin_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("marketplace_fee_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("shipping_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("provider_used", sa.String(40)),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("linked_purchase_id", sa.String(36), sa.ForeignKey("purchase_cases.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_market_studies_search_term", "market_studies", ["search_term"])
    op.create_index("ix_market_studies_created_at", "market_studies", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_market_studies_created_at", table_name="market_studies")
    op.drop_index("ix_market_studies_search_term", table_name="market_studies")
    op.drop_table("market_studies")
    op.drop_table("market_study_connector_config")
