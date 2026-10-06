"""expand product master data and channel listing drafts"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "35_product_master_catalog"
down_revision: str | None = "34_market_studies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for _name, column in (
        ("brand", sa.Column("brand", sa.String(120))),
        ("manufacturer", sa.Column("manufacturer", sa.String(160))),
        ("manufacturer_part_number", sa.Column("manufacturer_part_number", sa.String(120))),
        ("barcode", sa.Column("barcode", sa.String(32))),
        ("category", sa.Column("category", sa.String(160))),
        (
            "item_condition",
            sa.Column("item_condition", sa.String(24), nullable=False, server_default="new"),
        ),
        ("warranty_days", sa.Column("warranty_days", sa.Integer())),
        ("origin_country", sa.Column("origin_country", sa.String(80))),
        ("weight_g", sa.Column("weight_g", sa.Numeric(12, 3))),
        ("package_length_cm", sa.Column("package_length_cm", sa.Numeric(10, 2))),
        ("package_width_cm", sa.Column("package_width_cm", sa.Numeric(10, 2))),
        ("package_height_cm", sa.Column("package_height_cm", sa.Numeric(10, 2))),
        ("attributes", sa.Column("attributes", sa.JSON(), nullable=False, server_default="{}")),
        ("fitments", sa.Column("fitments", sa.JSON(), nullable=False, server_default="[]")),
        ("images", sa.Column("images", sa.JSON(), nullable=False, server_default="[]")),
    ):
        op.add_column("products", column)
    op.create_index(
        "ix_products_manufacturer_part_number", "products", ["manufacturer_part_number"]
    )
    op.create_index("ix_products_barcode", "products", ["barcode"])

    with op.batch_alter_table("product_marketplace_listings") as batch_op:
        batch_op.alter_column(
            "external_item_id",
            existing_type=sa.String(80),
            nullable=True,
        )
    op.add_column(
        "product_marketplace_listings",
        sa.Column("sync_status", sa.String(30), nullable=False, server_default="imported"),
    )
    op.add_column("product_marketplace_listings", sa.Column("sync_error", sa.Text()))
    op.add_column("product_marketplace_listings", sa.Column("category_id", sa.String(80)))
    op.add_column(
        "product_marketplace_listings",
        sa.Column("channel_data", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("product_marketplace_listings", "channel_data")
    op.drop_column("product_marketplace_listings", "category_id")
    op.drop_column("product_marketplace_listings", "sync_error")
    op.drop_column("product_marketplace_listings", "sync_status")
    has_drafts = op.get_bind().scalar(
        sa.text("SELECT 1 FROM product_marketplace_listings WHERE external_item_id IS NULL LIMIT 1")
    )
    if has_drafts:
        raise RuntimeError(
            "Remova ou publique os rascunhos de canais antes de reverter esta migration"
        )
    with op.batch_alter_table("product_marketplace_listings") as batch_op:
        batch_op.alter_column(
            "external_item_id",
            existing_type=sa.String(80),
            nullable=False,
        )
    op.drop_index("ix_products_barcode", table_name="products")
    op.drop_index("ix_products_manufacturer_part_number", table_name="products")
    for name in (
        "images",
        "fitments",
        "attributes",
        "package_height_cm",
        "package_width_cm",
        "package_length_cm",
        "weight_g",
        "origin_country",
        "warranty_days",
        "item_condition",
        "category",
        "barcode",
        "manufacturer_part_number",
        "manufacturer",
        "brand",
    ):
        op.drop_column("products", name)
