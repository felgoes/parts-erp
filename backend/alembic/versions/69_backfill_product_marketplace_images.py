"""backfill product galleries from marketplace listing pictures"""

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "69_backfill_product_marketplace_images"
down_revision: str | None = "68_normalize_product_attributes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def _json_value(value: object) -> object:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def upgrade() -> None:
    bind = op.get_bind()
    products = sa.table(
        "products",
        sa.column("id", sa.String),
        sa.column("images", sa.JSON),
    )
    listings = sa.table(
        "product_marketplace_listings",
        sa.column("product_id", sa.String),
        sa.column("provider", sa.String),
        sa.column("external_item_id", sa.String),
        sa.column("images", sa.JSON),
    )
    uploaded_at = datetime.now(UTC).isoformat()
    for product in bind.execute(sa.select(products.c.id, products.c.images)):
        current = _json_value(product.images)
        images = list(current) if isinstance(current, list) else []
        existing_urls = {
            str(image.get("url") or "")
            for image in images
            if isinstance(image, dict)
        }
        changed = False
        rows = bind.execute(
            sa.select(
                listings.c.provider,
                listings.c.external_item_id,
                listings.c.images,
            ).where(listings.c.product_id == product.id)
        )
        for listing in rows:
            listing_images = _json_value(listing.images)
            for photo in listing_images if isinstance(listing_images, list) else []:
                url = (
                    str(photo.get("secure_url") or photo.get("url") or "")
                    if isinstance(photo, dict)
                    else str(photo or "")
                )
                if not url or url in existing_urls:
                    continue
                url = url.replace("http://", "https://", 1) if url.startswith("http://") else url
                existing_urls.add(url)
                images.append(
                    {
                        "id": f"{listing.provider}-{hashlib.sha256(url.encode()).hexdigest()[:20]}",
                        "filename": "",
                        "url": url,
                        "position": len(images),
                        "width": int(photo.get("width") or 0) if isinstance(photo, dict) else 0,
                        "height": int(photo.get("height") or 0) if isinstance(photo, dict) else 0,
                        "uploaded_at": uploaded_at,
                        "source": listing.provider,
                        "external_item_id": listing.external_item_id,
                    }
                )
                changed = True
        if changed:
            bind.execute(
                products.update().where(products.c.id == product.id).values(images=images)
            )


def downgrade() -> None:
    # Marketplace photos are now part of the product gallery and should be retained.
    pass
