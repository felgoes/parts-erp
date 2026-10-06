"""track marketplace returns through receipt, inspection and restock"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "33_after_sale_returns"
down_revision: str | None = "32_stock_movement_costs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE movementtype ADD VALUE IF NOT EXISTS 'customer_return'")
    op.create_table(
        "after_sale_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("external_case_id", sa.String(100), nullable=False),
        sa.Column("marketplace_order_id", sa.String(36), sa.ForeignKey("marketplace_orders.id"), nullable=False),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("sales_invoices.id")),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("workflow_status", sa.String(30), nullable=False),
        sa.Column("marketplace_status", sa.String(60), nullable=False),
        sa.Column("reason", sa.String(500)),
        sa.Column("requested_by", sa.String(80)),
        sa.Column("payment_status", sa.String(40)),
        sa.Column("refund_amount", sa.Numeric(14, 2)),
        sa.Column("requested_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "external_case_id", name="uq_after_sale_provider_external"),
    )
    op.create_index("ix_after_sale_invoice", "after_sale_cases", ["invoice_id"])
    op.create_index("ix_after_sale_cases_workflow_status", "after_sale_cases", ["workflow_status"])
    op.create_table(
        "after_sale_case_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("after_sale_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invoice_item_id", sa.String(36), sa.ForeignKey("invoice_items.id")),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("requested_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("received_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("inspected_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("restocked_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("disposition", sa.String(30), nullable=False),
        sa.Column("notes", sa.String(500)),
    )
    op.create_index("ix_after_sale_case_items_case", "after_sale_case_items", ["case_id"])
    op.create_table(
        "after_sale_case_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("after_sale_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(60), nullable=False),
        sa.Column("detail", sa.String(500)),
        sa.Column("fingerprint", sa.String(180), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("case_id", "fingerprint", name="uq_after_sale_case_event_fingerprint"),
    )
    op.create_index(
        "ix_after_sale_case_events_case_created",
        "after_sale_case_events",
        ["case_id", "created_at"],
    )
    _backfill_existing_return_events()


def _backfill_existing_return_events() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    order_events = sa.Table("marketplace_order_events", metadata, autoload_with=bind)
    orders = sa.Table("marketplace_orders", metadata, autoload_with=bind)
    invoices = sa.Table("sales_invoices", metadata, autoload_with=bind)
    invoice_items = sa.Table("invoice_items", metadata, autoload_with=bind)
    cases = sa.Table("after_sale_cases", metadata, autoload_with=bind)
    case_items = sa.Table("after_sale_case_items", metadata, autoload_with=bind)
    case_events = sa.Table("after_sale_case_events", metadata, autoload_with=bind)
    existing: dict[tuple[str, str], str] = {}

    rows = bind.execute(
        sa.select(order_events, orders.c.provider, orders.c.external_order_id, orders.c.invoice_id)
        .select_from(order_events.join(orders, order_events.c.order_id == orders.c.id))
        .where(order_events.c.event_type == "after_sale")
        .order_by(order_events.c.created_at)
    ).mappings()
    for row in rows:
        payload = row["payload"] if isinstance(row["payload"], dict) else {}
        kind = str(payload.get("kind") or "")
        if kind not in {"return", "claim"}:
            continue
        provider = str(row["provider"] or "mercadolivre")
        external_id = str(payload.get("id") or f"event-{row['id']}")[:100]
        key = (provider, external_id)
        case_id = existing.get(key)
        if case_id is None:
            case_id = str(uuid4())
            existing[key] = case_id
            order_id = row["order_id"]
            invoice_id = row["invoice_id"]
            invoice = bind.execute(
                sa.select(invoices.c.id).where(invoices.c.id == invoice_id)
            ).first() if invoice_id else None
            requested_at = row["created_at"] or datetime.now(UTC)
            bind.execute(
                cases.insert().values(
                    id=case_id,
                    provider=provider,
                    external_case_id=external_id,
                    marketplace_order_id=order_id,
                    invoice_id=invoice[0] if invoice else None,
                    kind=kind,
                    workflow_status="requested",
                    marketplace_status=str(row["status"] or "unknown")[:60],
                    reason=payload.get("reason"),
                    requested_by=payload.get("requested_by"),
                    requested_at=requested_at,
                    payload={"notification": {"kind": kind, "status": row["status"], "id": external_id}},
                    created_at=requested_at,
                    updated_at=requested_at,
                )
            )
            if invoice:
                invoice_lines = bind.execute(
                    sa.select(invoice_items).where(invoice_items.c.invoice_id == invoice[0])
                ).mappings()
                for line in invoice_lines:
                    bind.execute(
                        case_items.insert().values(
                            id=str(uuid4()),
                            case_id=case_id,
                            invoice_item_id=line["id"],
                            product_id=line["product_id"],
                            sku=line["sku"],
                            description=line["description"],
                            requested_quantity=line["quantity"],
                            received_quantity=0,
                            inspected_quantity=0,
                            restocked_quantity=0,
                            disposition="pending",
                        )
                    )
        status = str(row["status"] or "unknown")[:60]
        fingerprint = f"marketplace:{kind}:{external_id}:{status}"[:180]
        if not bind.execute(
            sa.select(case_events.c.id).where(
                case_events.c.case_id == case_id,
                case_events.c.fingerprint == fingerprint,
            )
        ).first():
            bind.execute(
                case_events.insert().values(
                    id=str(uuid4()),
                    case_id=case_id,
                    event_type="marketplace_update",
                    status=status,
                    detail=payload.get("reason"),
                    fingerprint=fingerprint,
                    payload={key: value for key, value in payload.items() if key in {"kind", "status", "reason", "requested_by", "id", "created_at"}},
                    created_at=row["created_at"] or datetime.now(UTC),
                )
            )


def downgrade() -> None:
    op.drop_index("ix_after_sale_case_events_case_created", table_name="after_sale_case_events")
    op.drop_table("after_sale_case_events")
    op.drop_index("ix_after_sale_case_items_case", table_name="after_sale_case_items")
    op.drop_table("after_sale_case_items")
    op.drop_index("ix_after_sale_cases_workflow_status", table_name="after_sale_cases")
    op.drop_index("ix_after_sale_invoice", table_name="after_sale_cases")
    op.drop_table("after_sale_cases")
