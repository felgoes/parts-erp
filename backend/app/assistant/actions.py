"""Prévia, revalidação e execução confirmada das três escritas permitidas."""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MovementType, Product, User
from app.models.assistant import AssistantConversation, AssistantPendingAction
from app.schemas.products import ProductCreate
from app.schemas.purchases import PurchaseCreate, PurchaseItemCreate

ACTION_TTL = timedelta(minutes=30)


class ActionError(Exception):
    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _decimal(value: object, default: str = "0") -> Decimal:
    if value in (None, ""):
        return Decimal(default)
    text = str(value)
    return Decimal(text.replace(".", "").replace(",", ".")) if "," in text else Decimal(text)


def _num(value: object) -> str:
    number = Decimal(str(value)).normalize()
    text = f"{number:f}".rstrip("0").rstrip(".") if "." in f"{number:f}" else f"{number:f}"
    return text.replace(".", ",")


def _money(value: object) -> str:
    return f"{Decimal(str(value)):.2f}".replace(".", ",")


def _validation_message(error: ValidationError) -> str:
    first = error.errors()[0] if error.errors() else {}
    location = ".".join(str(part) for part in first.get("loc", ()))
    return f"{location}: {first.get('msg', 'dados inválidos')}" if location else str(first)


def _product_payload(args: dict) -> ProductCreate:
    return ProductCreate(
        sku=str(args.get("sku") or "").strip(),
        name=str(args.get("nome") or "").strip(),
        description=args.get("descricao") or None,
        brand=args.get("marca") or None,
        category=args.get("categoria") or None,
        barcode=args.get("codigo_barras") or None,
        sale_price=_decimal(args.get("preco_venda")),
        cost_price=_decimal(args.get("preco_custo")),
        current_stock=_decimal(args.get("estoque_inicial")),
        minimum_stock=_decimal(args.get("estoque_minimo")),
    )


def _purchase_payload(args: dict) -> PurchaseCreate:
    items = [
        PurchaseItemCreate(
            sku=str(item.get("sku") or "").strip(),
            description=str(item.get("descricao") or item.get("sku") or "").strip(),
            unit=str(item.get("unidade") or "un"),
            quantity=_decimal(item.get("quantidade")),
            unit_cost=_decimal(item.get("custo_unitario")),
        )
        for item in args.get("itens") or []
    ]
    return PurchaseCreate(
        purchase_type=args.get("tipo") or "parts",
        supplier_name=args.get("fornecedor") or None,
        supplier_order_number=args.get("numero_pedido") or None,
        purchase_origin=args.get("origem") or None,
        expense_category=args.get("categoria_despesa") or None,
        expense_amount=_decimal(args["valor_despesa"]) if args.get("valor_despesa") else None,
        expense_description=args.get("descricao_despesa") or None,
        payment_type=args.get("pagamento") or "cash",
        installment_count=int(args.get("parcelas") or 1),
        first_due_days=int(args.get("primeiro_vencimento_dias") or 0),
        notes=args.get("observacoes") or None,
        items=items,
    )


def _summary_product(payload: ProductCreate) -> str:
    return (
        f"Criar produto {payload.sku} — {payload.name}. "
        f"Venda R$ {_money(payload.sale_price)}, custo R$ {_money(payload.cost_price)}, "
        f"saldo inicial {_num(payload.current_stock)}, mínimo {_num(payload.minimum_stock)}."
    )


def _summary_purchase(payload: PurchaseCreate) -> str:
    if payload.purchase_type == "expense":
        detail = (
            f"Despesa {payload.expense_category} de R$ {_money(payload.expense_amount)}"
            f"{' — ' + payload.expense_description if payload.expense_description else ''}"
        )
    else:
        lines = ", ".join(
            f"{item.quantity} × {item.sku or item.description}" for item in payload.items
        )
        detail = f"Compra de peças com {len(payload.items)} item(ns): {lines}"
    supplier = f" Fornecedor: {payload.supplier_name}." if payload.supplier_name else ""
    payment = (
        f" Pagamento: {payload.payment_type}, {payload.installment_count} parcela(s)."
        if payload.purchase_type == "expense"
        else " Custos entram pela cotação do fornecedor."
    )
    return f"{detail}.{supplier}{payment}"


def create_pending(
    db: Session,
    *,
    conversation: AssistantConversation,
    user: User,
    tool_name: str,
    args: dict,
) -> dict:
    try:
        if tool_name == "prever_produto":
            payload = _product_payload(args).model_dump(mode="json")
            if db.scalar(select(Product).where(Product.sku == payload["sku"])):
                return {"status": "blocked", "erro": "Já existe produto com esse SKU."}
            summary = _summary_product(_product_payload(args))
        elif tool_name == "prever_compra":
            purchase = _purchase_payload(args)
            if purchase.purchase_type == "parts" and any(
                item.unit_cost > 0 for item in purchase.items
            ):
                return {
                    "status": "blocked",
                    "erro": (
                        "Compra de peças nasce sem valor; custo, frete e desconto entram pela "
                        "cotação do fornecedor."
                    ),
                }
            payload = purchase.model_dump(mode="json")
            summary = _summary_purchase(purchase)
        elif tool_name == "prever_ajuste_estoque":
            product = _resolve_product(db, args)
            quantity = _decimal(args.get("quantidade"))
            if str(args.get("operacao") or "") == "saida":
                quantity = -abs(quantity)
            if quantity == 0:
                return {"status": "blocked", "erro": "Informe uma quantidade diferente de zero."}
            reason = str(args.get("motivo") or "").strip()
            if not reason:
                return {"status": "blocked", "erro": "Informe o motivo do ajuste."}
            new_balance = Decimal(product.current_stock) + quantity
            if new_balance < 0:
                return {
                    "status": "blocked",
                    "erro": (
                        f"Saldo insuficiente para {product.sku}: disponível "
                        f"{product.current_stock}."
                    ),
                }
            payload = {
                "product_id": product.id,
                "sku": product.sku,
                "quantity": str(quantity),
                "reason": reason,
                "balance_before": str(product.current_stock),
                "balance_after": str(new_balance),
            }
            summary = (
                f"Ajustar estoque de {product.sku} ({product.name}): "
                f"{_num(product.current_stock)} → {_num(new_balance)} "
                f"({_num(quantity)}). Motivo: {reason}. "
                "Pode haver sincronização com os canais de venda."
            )
        else:
            return {"status": "blocked", "erro": "Ação não permitida."}
    except ValidationError as error:
        return {"status": "blocked", "erro": _validation_message(error)}
    except (ValueError, InvalidOperation, ActionError) as error:
        if isinstance(error, ActionError):
            return {"status": "blocked", "erro": error.message}
        return {"status": "blocked", "erro": f"Dados inválidos: {error}"}

    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    action = AssistantPendingAction(
        conversation_id=conversation.id,
        user_id=user.id,
        tool_name=tool_name,
        payload=payload,
        summary=summary,
        fingerprint=hashlib.sha256(serialized.encode()).hexdigest(),
        idempotency_key=f"assistant:{uuid.uuid4().hex}",
        expires_at=datetime.now(UTC) + ACTION_TTL,
    )
    db.add(action)
    db.commit()
    return {
        "status": "pending_confirmation",
        "action_id": action.id,
        "summary": summary,
        "expires_at": action.expires_at.isoformat().replace("+00:00", "Z"),
        "aviso": "Nada foi gravado. Peça confirmação explícita antes de executar.",
    }


def _resolve_product(db: Session, args: dict) -> Product:
    product_id = str(args.get("product_id") or "").strip()
    sku = str(args.get("sku") or "").strip()
    if product_id:
        product = db.get(Product, product_id)
        if product:
            return product
    if sku:
        matches = list(db.scalars(select(Product).where(Product.sku.ilike(f"%{sku}%")).limit(6)))
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise ActionError("Produto não encontrado.", 404)
        raise ActionError(
            "Mais de um produto corresponde ao SKU informado: "
            + ", ".join(item.sku for item in matches),
            409,
        )
    raise ActionError("Informe o produto por id ou SKU.", 422)


def pending_action(db: Session, user: User, action_id: str) -> AssistantPendingAction:
    action = db.scalar(
        select(AssistantPendingAction)
        .where(AssistantPendingAction.id == action_id)
        .with_for_update()
    )
    if action is None or action.user_id != user.id:
        raise HTTPException(status_code=404, detail="Ação não encontrada")
    return action


def cancel(db: Session, user: User, action: AssistantPendingAction) -> dict:
    if action.status == "pending":
        action.status = "cancelled"
        db.commit()
    return {"status": action.status, "message": "Nenhuma alteração foi feita."}


def execute(db: Session, user: User, action: AssistantPendingAction) -> dict:
    if action.conversation_id is None:
        raise ActionError("A conversa desta prévia foi excluída; gere uma nova prévia.")
    if action.status == "executed":
        return {"status": "executed", "message": "Esta ação já foi executada anteriormente."}
    if action.status != "pending":
        raise ActionError("Esta ação não está mais pendente.")
    if action.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        action.status = "expired"
        db.commit()
        raise ActionError("A prévia expirou; gere uma nova antes de confirmar.")
    if action.tool_name == "prever_produto":
        result = _execute_product(db, user, action)
    elif action.tool_name == "prever_compra":
        result = _execute_purchase(db, user, action)
    elif action.tool_name == "prever_ajuste_estoque":
        result = _execute_adjustment(db, action)
    else:
        raise ActionError("Ação não permitida.")
    action.status = "executed"
    action.executed_at = datetime.now(UTC)
    action.payload = {**action.payload, "result": result}
    db.commit()
    return result


def _execute_product(db: Session, user: User, action: AssistantPendingAction) -> dict:
    from app.api.routes.products import create_product

    if db.scalar(select(Product).where(Product.sku == action.payload["sku"])):
        raise ActionError("Já existe produto com esse SKU; a ação não foi repetida.")
    try:
        product = create_product(ProductCreate(**action.payload), db, user)
    except HTTPException as error:
        raise ActionError(str(error.detail), error.status_code) from error
    return {
        "status": "created",
        "product_id": product.id,
        "sku": product.sku,
        "message": "Produto criado.",
    }


def _execute_purchase(db: Session, user: User, action: AssistantPendingAction) -> dict:
    from app.api.routes.purchases_creation import create_purchase
    from app.models import PurchaseCase

    marker = f"Assistente IA: {action.id}"
    existing = db.scalar(
        select(PurchaseCase).where(PurchaseCase.notes.ilike(f"%{marker}%")).limit(1)
    )
    if existing:
        return {
            "status": "created",
            "purchase_id": existing.id,
            "number": existing.number,
            "message": "Compra já havia sido criada; nada foi duplicado.",
        }
    payload = {**action.payload}
    payload["notes"] = f"{payload.get('notes') or ''}\n{marker}".strip()
    try:
        purchase = create_purchase(PurchaseCreate(**payload), db, user)
    except HTTPException as error:
        raise ActionError(str(error.detail), error.status_code) from error
    return {
        "status": "created",
        "purchase_id": purchase.id,
        "number": purchase.number,
        "message": "Compra criada.",
    }


def _execute_adjustment(db: Session, action: AssistantPendingAction) -> dict:
    from app.services.product_channels import sync_product_stock_all
    from app.services.stock import move_stock

    product = db.get(Product, action.payload["product_id"])
    if product is None:
        raise ActionError("Produto não encontrado.", 404)
    if str(product.current_stock) != str(Decimal(action.payload["balance_before"])):
        action.status = "stale"
        db.commit()
        raise ActionError(
            "O saldo mudou desde a prévia; peça uma nova confirmação com os valores atuais."
        )
    movement = move_stock(
        db,
        product_id=product.id,
        quantity=Decimal(action.payload["quantity"]),
        movement_type=MovementType.adjustment,
        reason=action.payload["reason"],
        reference=None,
        idempotency_key=f"assistant:{action.id}",
    )
    db.commit()
    db.refresh(product)
    try:
        sync_product_stock_all(db, product)
        synced = "sincronização com canais solicitada"
    except Exception:
        db.rollback()
        synced = "saldo local gravado; sincronização com canais pendente"
    return {
        "status": "adjusted",
        "product_id": product.id,
        "sku": product.sku,
        "movement_id": movement.id,
        "balance": str(product.current_stock),
        "message": f"Estoque ajustado; {synced}.",
    }


def action_view(action: AssistantPendingAction) -> dict:
    now = datetime.now(UTC)
    expires = action.expires_at.replace(tzinfo=UTC)
    created = action.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return {
        "id": action.id,
        "conversation_id": action.conversation_id,
        "summary": action.summary,
        "status": action.status,
        "tool": action.tool_name,
        "created_at": created.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "expires_at": expires.isoformat().replace("+00:00", "Z"),
        "expired": expires < now and action.status == "pending",
    }
