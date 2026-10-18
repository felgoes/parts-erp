from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assistant import actions, tool_reads
from app.models import Product, StockMovement, User, UserRole
from app.models.assistant import AssistantConversation


def admin(db: Session) -> User:
    user = User(
        email="assistant-stock@example.test",
        full_name="Admin",
        password_hash="x",
        role=UserRole.admin,
    )
    db.add(user)
    db.commit()
    return user


def test_stock_adjustment_confirmation_updates_balance_once(db):
    user = admin(db)
    chat = AssistantConversation(user_id=user.id)
    db.add(chat)
    db.commit()
    product = Product(sku="EST-2", name="Cabo", current_stock=5, sale_price=10)
    db.add(product)
    db.commit()
    preview = actions.create_pending(
        db,
        conversation=chat,
        user=user,
        tool_name="prever_ajuste_estoque",
        args={
            "sku": "EST-2",
            "operacao": "entrada",
            "quantidade": 2,
            "motivo": "Inventário",
        },
    )
    action = actions.pending_action(db, user, preview["action_id"])
    result = actions.execute(db, user, action)
    assert result["balance"] == "7.000"
    db.refresh(product)
    assert product.current_stock == Decimal("7")
    movement = db.scalar(select(StockMovement))
    assert movement.idempotency_key.startswith("assistant:")


def test_product_query_without_term_lists_active_stock(db):
    db.add_all(
        [
            Product(sku="L-1", name="Filtro", current_stock=4, active=True),
            Product(sku="L-2", name="Rolamento", current_stock=2, active=True),
            Product(sku="L-3", name="Inativo", current_stock=9, active=False),
        ]
    )
    db.commit()
    result = tool_reads.buscar_produtos(db, "", 50)
    assert result["total"] == 2
    assert result["truncado"] is False
    assert {item["sku"] for item in result["produtos"]} == {"L-1", "L-2"}
    limited = tool_reads.buscar_produtos(db, "", 1)
    assert limited["truncado"] is True
    assert len(limited["produtos"]) == 1
