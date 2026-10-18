import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.assistant import actions, tool_reads
from app.assistant.providers import ModelReply, ToolCall
from app.assistant.service import run_turn
from app.core.security import encrypt_secret
from app.db.session import get_db
from app.main import app
from app.models import (
    InvoiceDocument,
    InvoiceSource,
    InvoiceStatus,
    MarketplaceOrder,
    MarketplaceOrderEvent,
    Product,
    PurchaseCase,
    SalesInvoice,
    StockMovement,
    User,
    UserRole,
)
from app.models.assistant import (
    AssistantConfiguration,
    AssistantConversation,
    AssistantMessage,
    AssistantPendingAction,
)


def admin(db: Session, email: str = "assistant@example.test") -> User:
    user = User(email=email, full_name="Admin", password_hash="x", role=UserRole.admin)
    db.add(user)
    db.commit()
    return user


def configured(db: Session, budget: str = "5.00") -> None:
    db.add(
        AssistantConfiguration(
            id="shared",
            provider="openai",
            model="gpt-4.1-mini",
            encrypted_api_key=encrypt_secret("test-key"),
            monthly_budget_usd=Decimal(budget),
        )
    )
    db.commit()


def conversation(db: Session, user: User) -> AssistantConversation:
    row = AssistantConversation(user_id=user.id)
    db.add(row)
    db.commit()
    return row


def sequence(monkeypatch, replies: list[ModelReply]):
    remaining = list(replies)
    calls: list[list[dict]] = []

    def fake_complete(provider, model, api_key, messages, tools):
        calls.append(messages)
        return remaining.pop(0)

    monkeypatch.setattr("app.assistant.service.complete", fake_complete)
    return calls


def test_chat_uses_tools_and_persists_only_final_answer(db, monkeypatch):
    user = admin(db)
    configured(db)
    chat = conversation(db, user)
    db.add_all(
        [
            Product(sku="F-1", name="Filtro de óleo", current_stock=4, sale_price=20),
            Product(sku="F-2", name="Filtro de ar", current_stock=7, sale_price=30),
        ]
    )
    db.commit()
    calls = sequence(
        monkeypatch,
        [
            ModelReply("", [ToolCall("c1", "buscar_produtos", {"termo": "filtro"})]),
            ModelReply("Encontrei dois filtros; qual deles você quer consultar?"),
        ],
    )
    result = run_turn(db, user, chat, "Quanto tem de filtro?")
    assert result["message"].startswith("Encontrei dois filtros")
    assert len(calls) == 2
    tool_payload = json.loads(calls[1][-1]["content"])
    assert tool_payload["ambiguo"] is True
    roles = list(
        db.scalars(
            select(AssistantMessage.role)
            .where(AssistantMessage.conversation_id == chat.id)
            .order_by(AssistantMessage.created_at, AssistantMessage.id)
        )
    )
    assert roles == ["user", "assistant"]


def test_preview_does_not_write_and_confirmation_is_idempotent(db, monkeypatch):
    user = admin(db)
    configured(db)
    chat = conversation(db, user)
    sequence(
        monkeypatch,
        [
            ModelReply(
                "",
                [
                    ToolCall(
                        "c1",
                        "prever_produto",
                        {
                            "sku": "NOVO-1",
                            "nome": "Pastilha de freio",
                            "preco_venda": 120,
                            "preco_custo": 70,
                            "estoque_inicial": 5,
                        },
                    )
                ],
            ),
            ModelReply("A prévia está pronta para confirmação."),
        ],
    )
    result = run_turn(db, user, chat, "Cadastre a pastilha NOVO-1")
    assert result["pending_actions"][0]["status"] == "pending_confirmation"
    assert db.scalar(select(func.count()).select_from(Product).where(Product.sku == "NOVO-1")) == 0
    action_id = result["pending_actions"][0]["action_id"]

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with TestClient(app) as client:
            first = client.post(f"/api/v1/assistant/actions/{action_id}/confirm")
            assert first.status_code == 200
            assert first.json()["result"]["status"] == "created"
            second = client.post(f"/api/v1/assistant/actions/{action_id}/confirm")
            assert second.status_code == 200
            assert second.json()["result"]["status"] == "executed"
    finally:
        app.dependency_overrides.clear()
    assert db.scalar(select(func.count()).select_from(Product).where(Product.sku == "NOVO-1")) == 1
    assert (
        db.scalar(
            select(func.count())
            .select_from(StockMovement)
            .where(StockMovement.idempotency_key.like("initial:%"))
        )
        == 1
    )


def test_cancelled_and_ambiguous_actions_do_not_write(db):
    user = admin(db)
    chat = conversation(db, user)
    db.add_all(
        [
            Product(sku="A-1", name="Filtro A", current_stock=1),
            Product(sku="A-2", name="Filtro A reforçado", current_stock=1),
        ]
    )
    db.commit()
    blocked = actions.create_pending(
        db,
        conversation=chat,
        user=user,
        tool_name="prever_ajuste_estoque",
        args={"sku": "A-", "operacao": "entrada", "quantidade": 1, "motivo": "teste"},
    )
    assert blocked["status"] == "blocked"
    assert "Mais de um produto" in blocked["erro"]
    assert db.scalar(select(func.count()).select_from(StockMovement)) == 0


def test_stock_preview_and_stale_balance_forces_new_confirmation(db, monkeypatch):
    user = admin(db)
    configured(db)
    chat = conversation(db, user)
    product = Product(sku="EST-1", name="Rolamento", current_stock=10, sale_price=50)
    db.add(product)
    db.commit()
    sequence(
        monkeypatch,
        [
            ModelReply(
                "",
                [
                    ToolCall(
                        "c1",
                        "prever_ajuste_estoque",
                        {
                            "sku": "EST-1",
                            "operacao": "saida",
                            "quantidade": 3,
                            "motivo": "Avaria",
                        },
                    )
                ],
            ),
            ModelReply("Confirme o ajuste de 10 para 7."),
        ],
    )
    result = run_turn(db, user, chat, "Ajuste o estoque do rolamento")
    action_id = result["pending_actions"][0]["action_id"]
    product.current_stock = Decimal("8")
    db.commit()
    action = actions.pending_action(db, user, action_id)
    with pytest.raises(actions.ActionError) as captured:
        actions.execute(db, user, action)
    assert "saldo mudou" in captured.value.message
    assert db.scalar(select(func.count()).select_from(StockMovement)) == 0


def test_budget_alerts_then_blocks_without_calling_provider_again(db, monkeypatch):
    user = admin(db)
    configured(db, "0.01")
    chat = conversation(db, user)
    calls = sequence(
        monkeypatch, [ModelReply("Resposta cara", [], 100_000, 100_000)]
    )
    first = run_turn(db, user, chat, "Olá")
    assert first["budget"]["alert"] is True
    assert first["budget"]["blocked"] is True
    with pytest.raises(Exception) as captured:
        run_turn(db, user, chat, "Outra")
    assert "limite mensal" in str(captured.value)
    assert len(calls) == 1


def test_fiscal_investigation_uses_local_records_and_redacts_secrets(db):
    invoice = SalesInvoice(
        number="VEN-9",
        status=InvoiceStatus.confirmed,
        source=InvoiceSource.mercadolivre,
        marketplace_order_id="ML-9",
        total=Decimal("99.90"),
        issued_at=datetime.now(UTC),
    )
    db.add(invoice)
    db.commit()
    order = MarketplaceOrder(
        provider="mercadolivre",
        external_order_id="ML-9",
        seller_id="seller",
        status="paid",
        invoice_id=invoice.id,
        fiscal_status="error",
        fiscal_error="falha sk-ABC123456789 contato cliente@example.com",
        payload={"last_updated": 1_700_000_000},
    )
    db.add(order)
    db.commit()
    db.add_all(
        [
            MarketplaceOrderEvent(
                order_id=order.id,
                event_type="fiscal_status",
                status="error",
                detail="Bearer abcdefghijklmnop",
            ),
            InvoiceDocument(
                invoice_id=invoice.id,
                external_id="nfe-1",
                document_type="xml",
                filename="nfe-9.xml",
                storage_path="/private/never-exposed.xml",
                sha256="0" * 64,
            ),
        ]
    )
    db.commit()
    evidence = tool_reads.investigar_fiscal(db, "ML-9")
    serialized = json.dumps(evidence)
    assert evidence["consulta_externa"] is False
    assert evidence["pedido"]["estado_fiscal"] == "error"
    assert evidence["nota_fiscal"]["presente"] is False
    assert "sk-ABC" not in serialized
    assert "cliente@example.com" not in serialized
    assert "abcdefghijklmnop" not in serialized
    assert "/private" not in serialized


def test_parts_purchase_with_cost_is_blocked_before_loading_preview(db):
    user = admin(db)
    chat = conversation(db, user)
    result = actions.create_pending(
        db,
        conversation=chat,
        user=user,
        tool_name="prever_compra",
        args={
            "tipo": "parts",
            "fornecedor": "Peças Sul",
            "itens": [{"descricao": "Filtro", "quantidade": 2, "custo_unitario": 10}],
        },
    )
    assert result["status"] == "blocked"
    assert "cotação" in result["erro"]
    assert db.scalar(select(func.count()).select_from(AssistantPendingAction)) == 0
    assert db.scalar(select(func.count()).select_from(PurchaseCase)) == 0


def test_expense_preview_confirmation_creates_once(db, monkeypatch):
    user = admin(db)
    configured(db)
    chat = conversation(db, user)
    sequence(
        monkeypatch,
        [
            ModelReply(
                "",
                [
                    ToolCall(
                        "c1",
                        "prever_compra",
                        {
                            "tipo": "expense",
                            "categoria_despesa": "Ferramentas",
                            "valor_despesa": 150.5,
                            "descricao_despesa": "Chave de torque",
                            "pagamento": "cash",
                        },
                    )
                ],
            ),
            ModelReply("Confirme a despesa de R$ 150,50."),
        ],
    )
    result = run_turn(db, user, chat, "Lance uma despesa de ferramentas")
    action_id = result["pending_actions"][0]["action_id"]
    action = actions.pending_action(db, user, action_id)
    first = actions.execute(db, user, action)
    second = actions.execute(db, user, action)
    assert first["status"] == "created"
    assert second["status"] == "executed"
    assert db.scalar(select(func.count()).select_from(PurchaseCase)) == 1
    purchase = db.scalar(select(PurchaseCase))
    assert "Assistente IA" in (purchase.notes or "")


def test_chat_rejects_non_admin_before_touching_provider(db, monkeypatch):
    operator = User(
        email="operator-chat@example.test",
        full_name="Operador",
        password_hash="x",
        role=UserRole.operator,
    )
    db.add(operator)
    db.commit()
    chat = conversation(db, operator)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: operator
    calls = sequence(monkeypatch, [ModelReply("não deveria responder")])
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/assistant/conversations/{chat.id}/messages",
                json={"message": "oi"},
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403
    assert calls == []
