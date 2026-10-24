from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MarketplaceAccount, MarketplaceOrder
from app.services.tracking_destination import tracking_destination_address


def refresh_shipping_destination(db: Session, order: MarketplaceOrder) -> None:
    if tracking_destination_address(order) or not order.shipment_id:
        return
    account = db.scalar(
        select(MarketplaceAccount).where(
            MarketplaceAccount.provider == "mercadolivre",
            MarketplaceAccount.seller_id == order.seller_id,
            MarketplaceAccount.active.is_(True),
        )
    )
    if not account:
        return
    try:
        from app.integrations.mercadolivre.sync import sync_shipping_status

        sync_shipping_status(db, order, account)
        db.commit()
    except Exception:
        db.rollback()
