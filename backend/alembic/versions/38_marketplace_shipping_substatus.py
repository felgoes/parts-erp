"""persist Mercado Livre shipment substatus for fulfillment UX"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "38_marketplace_shipping_substatus"
down_revision: str | None = "37_company_backup_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "marketplace_orders",
        sa.Column("shipping_substatus", sa.String(length=80), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("marketplace_orders", "shipping_substatus")
