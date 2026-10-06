from datetime import UTC, datetime
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
    select,
)

from app.core.security import encrypt_secret
from app.integrations.mercadolivre import sync as sync_module
from app.integrations.mercadolivre.client import MercadoLivreClient
from app.models import MarketplaceAccount, Product, SalesInvoice
from app.schemas.common import InvoiceOut


def test_marketplace_invoice_uses_original_order_date_on_create_and_resync(db, monkeypatch):
    account = MarketplaceAccount(
        seller_id="77",
        encrypted_access_token=encrypt_secret("token"),
        active=True,
    )
    db.add(account)
    db.add(
        Product(
            sku="ORDER-DATE-001",
            name="Sensor",
            sale_price=Decimal("45.00"),
            current_stock=Decimal("5"),
            minimum_stock=Decimal("1"),
        )
    )
    db.commit()
    order = {
        "id": 123,
        "seller": {"id": 77},
        "status": "paid",
        "date_created": "2026-09-29T23:30:00.000-04:00",
        "buyer": {"id": 9, "first_name": "Ana", "last_name": "Silva"},
        "order_items": [
            {"item": {"seller_sku": "ORDER-DATE-001"}, "quantity": 1, "unit_price": 45}
        ],
    }
    monkeypatch.setattr(
        MercadoLivreClient,
        "get",
        lambda self, path, **_kwargs: [] if path.endswith("/shipments") else order,
    )
    monkeypatch.setattr(
        sync_module,
        "automate_order_documents",
        lambda session, record, connected_account: record,
    )

    record = sync_module.sync_order(db, "77", "/orders/123")
    invoice = db.scalar(select(SalesInvoice).where(SalesInvoice.id == record.invoice_id))
    original_order_date = datetime(2026, 9, 30, 3, 30, tzinfo=UTC)
    assert invoice is not None
    assert invoice.issued_at == original_order_date

    invoice.issued_at = datetime(2026, 10, 4, 7, 0, tzinfo=UTC)
    db.commit()
    sync_module.sync_order(db, "77", "/orders/123")
    db.refresh(invoice)
    assert invoice.issued_at == original_order_date.replace(tzinfo=None)
    serialized = InvoiceOut.model_validate(invoice).model_dump(mode="json")
    assert serialized["issued_at"] == "2026-09-30T03:30:00Z"


def test_backfill_migration_repairs_existing_marketplace_invoice_dates():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    invoices = Table(
        "sales_invoices",
        metadata,
        Column("id", String, primary_key=True),
        Column("issued_at", DateTime(timezone=True)),
    )
    orders = Table(
        "marketplace_orders",
        metadata,
        Column("invoice_id", String),
        Column("payload", JSON),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(invoices),
            {"id": "invoice-1", "issued_at": datetime(2026, 10, 4, 7, tzinfo=UTC)},
        )
        connection.execute(
            insert(orders),
            {
                "invoice_id": "invoice-1",
                "payload": {"date_created": "2026-09-29T23:30:00.000-04:00"},
            },
        )
        migration_path = (
            Path(__file__).parents[1]
            / "alembic"
            / "versions"
            / "29_backfill_marketplace_invoice_dates.py"
        )
        spec = spec_from_file_location("backfill_marketplace_dates", migration_path)
        assert spec and spec.loader
        migration = module_from_spec(spec)
        spec.loader.exec_module(migration)
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
        repaired = connection.execute(
            select(invoices.c.issued_at).where(invoices.c.id == "invoice-1")
        ).scalar_one()

    assert repaired == datetime(2026, 9, 30, 3, 30)
