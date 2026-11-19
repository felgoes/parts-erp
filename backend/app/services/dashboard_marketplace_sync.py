from datetime import UTC, date, datetime, time
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.periods import BRAZIL_TZ as TZ
from app.integrations.mercadolivre.client import MercadoLivreClient
from app.integrations.mercadolivre.ml_orders import sync_order
from app.integrations.mercadolivre.ml_support import _resource_ids
from app.models import MarketplaceAccount, MarketplaceDashboardSync


def sync_dashboard_orders_for_period(
    db: Session, account: MarketplaceAccount, start: date, end: date
):
    state = db.scalar(
        select(MarketplaceDashboardSync).where(
            MarketplaceDashboardSync.account_id == account.id,
            MarketplaceDashboardSync.period_start == start,
            MarketplaceDashboardSync.period_end == end,
        )
    )
    now = datetime.now(UTC)
    if state is None:
        state = MarketplaceDashboardSync(
            account_id=account.id,
            period_start=start,
            period_end=end,
            sync_status="running",
            partial=False,
            last_attempt_at=now,
        )
        db.add(state)
    else:
        state.sync_status, state.sync_error, state.last_attempt_at, state.partial = (
            "running",
            None,
            now,
            False,
        )
    db.commit()
    try:
        first = datetime.combine(start, time.min, TZ).isoformat(timespec="seconds")
        last = datetime.combine(end, time(23, 59, 59), TZ).isoformat(timespec="seconds")
        params = {
            "seller": account.seller_id,
            "order.date_created.from": first,
            "order.date_created.to": last,
            "sort": "date_desc",
            "limit": 50,
        }
        offset = 0
        seen = set()
        while True:
            params["offset"] = offset
            response = MercadoLivreClient(db, account).get("/orders/search?" + urlencode(params))
            if not isinstance(response, dict):
                raise ValueError("Resposta de busca de pedidos inválida")
            paging = response.get("paging") or {}
            total = int(paging.get("total") or 0)
            ids = _resource_ids(response)
            if len(ids) != len(set(ids)) or any(value in seen for value in ids):
                state.partial = True
            if not ids and offset < total:
                state.partial = True
                break
            for order_id in ids:
                if order_id in seen:
                    state.partial = True
                    continue
                seen.add(order_id)
                sync_order(db, account.seller_id, f"/orders/{order_id}")
            offset += len(ids)
            if not ids or offset >= total:
                break
        if offset < total:
            state.partial = True
        state.sync_status, state.sync_error = "succeeded", None
        state.last_success_at = datetime.now(UTC)
        db.commit()
        return len(seen)
    except Exception as exc:
        db.rollback()
        state = db.scalar(
            select(MarketplaceDashboardSync).where(
                MarketplaceDashboardSync.account_id == account.id,
                MarketplaceDashboardSync.period_start == start,
                MarketplaceDashboardSync.period_end == end,
            )
        )
        if state:
            state.sync_status, state.sync_error = "failed", str(exc)[:500]
            state.last_attempt_at = datetime.now(UTC)
            db.commit()
        raise
