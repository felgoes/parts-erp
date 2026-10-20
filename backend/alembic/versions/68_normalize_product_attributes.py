"""normalize legacy empty product attribute arrays"""

from collections.abc import Sequence

from alembic import op

revision: str = "68_normalize_product_attributes"
down_revision: str | None = "67_assistant_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE products
        SET attributes = '{}'
        WHERE attributes IS NULL OR CAST(attributes AS TEXT) = '[]'
        """
    )


def downgrade() -> None:
    # Keep normalized values: reverting them would reintroduce invalid API responses.
    pass
