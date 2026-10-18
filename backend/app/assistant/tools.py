"""Catálogo de ferramentas e despacho para as implementações do ERP."""

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.assistant import actions, tool_ops, tool_reads
from app.assistant.actions import ActionError
from app.models import User
from app.models.assistant import AssistantConversation

PRODUCT_SCHEMA = {
    "type": "object",
    "properties": {
        "termo": {"type": "string", "description": "Nome, SKU ou código de barras."},
        "limite": {"type": "integer", "minimum": 1, "maximum": 100},
        "abaixo_minimo": {
            "type": "boolean",
            "description": "Restringe aos produtos com saldo abaixo do estoque mínimo.",
        },
    },
}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "buscar_produtos",
        "description": (
            "Consulta produtos e saldos no ERP. Sem termo, lista os produtos ativos — use isso "
            "para perguntas como 'quanto há de cada produto?'. Com termo, filtra por nome, SKU "
            "ou código de barras; se houver mais de um resultado, pergunte qual antes de agir."
        ),
        "parameters": PRODUCT_SCHEMA,
    },
    {
        "name": "consultar_vendas",
        "description": (
            "Localiza vendas, faturas e pedidos de marketplace no ERP por número, id ou pedido."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "identificador": {"type": "string", "description": "Número ou id da venda."}
            },
            "required": ["identificador"],
        },
    },
    {
        "name": "listar_vendas",
        "description": (
            "Lista vendas e pedidos recentes com status do pedido, envio, etiqueta e fiscal. "
            "Use para perguntas abertas como 'tem alguma venda para enviar?' ou 'quais vendas "
            "estão pendentes?'. Use pendentes_envio=true para pedidos prontos para envio."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "status_pedido": {"type": "string"},
                "status_envio": {"type": "string"},
                "pendentes_envio": {"type": "boolean"},
                "limite": {"type": "integer", "minimum": 1, "maximum": 50},
            },
        },
    },
    {
        "name": "investigar_fiscal",
        "description": (
            "Investiga a situação fiscal de uma venda usando apenas estados, documentos e logs "
            "locais do ERP. Não consulta o marketplace. Se faltar evidência, diga isso."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "identificador": {"type": "string", "description": "Número ou id da venda."}
            },
            "required": ["identificador"],
        },
    },
    {
        "name": "listar_compras",
        "description": "Lista compras recentes do ERP por número, fornecedor ou status.",
        "parameters": {
            "type": "object",
            "properties": {
                "busca": {"type": "string"},
                "status": {"type": "string"},
            },
        },
    },
    {
        "name": "resumo_operacional",
        "description": (
            "Resume o dia: vendas de hoje e do mês, pedidos prontos para envio, erros fiscais, "
            "produtos abaixo do mínimo e contas vencidas. Use para 'como está a operação hoje?'."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "listar_contas_a_pagar",
        "description": (
            "Lista contas a pagar com saldo, vencimento e atraso. Use vencidas=true para "
            "títulos já vencidos."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "vencidas": {"type": "boolean"},
                "status": {"type": "string", "enum": ["open", "paid", "cancelled"]},
                "limite": {"type": "integer", "minimum": 1, "maximum": 50},
            },
        },
    },
    {
        "name": "buscar_clientes",
        "description": (
            "Busca clientes por nome, documento, e-mail ou telefone e mostra o total comprado. "
            "Sem termo, lista os clientes cadastrados."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "termo": {"type": "string"},
                "limite": {"type": "integer", "minimum": 1, "maximum": 30},
            },
        },
    },
    {
        "name": "movimentacoes_estoque",
        "description": (
            "Mostra as movimentações de estoque recentes, com motivo, quantidade e saldo após. "
            "Informe o SKU para filtrar um produto."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sku": {"type": "string"},
                "limite": {"type": "integer", "minimum": 1, "maximum": 50},
            },
        },
    },
    {
        "name": "listar_erros_fiscais",
        "description": (
            "Lista pedidos com erro fiscal registrado, incluindo o motivo local. Não consulta o "
            "marketplace."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limite": {"type": "integer", "minimum": 1, "maximum": 30}
            },
        },
    },
    {
        "name": "detalhar_venda",
        "description": (
            "Abre o detalhe de uma venda: cliente, itens, totais, documentos, envio, etiqueta, "
            "estado fiscal e eventos locais. Use quando o administrador já informou a venda."
        ),
        "parameters": {
            "type": "object",
            "properties": {"identificador": {"type": "string"}},
            "required": ["identificador"],
        },
    },
    {
        "name": "prever_produto",
        "description": (
            "Valida e prepara a criação de um produto. Não grava nada: devolve uma prévia que "
            "o administrador precisa confirmar na interface."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sku": {"type": "string"},
                "nome": {"type": "string"},
                "descricao": {"type": "string"},
                "marca": {"type": "string"},
                "categoria": {"type": "string"},
                "codigo_barras": {"type": "string"},
                "preco_venda": {"type": "number", "minimum": 0},
                "preco_custo": {"type": "number", "minimum": 0},
                "estoque_inicial": {"type": "number"},
                "estoque_minimo": {"type": "number", "minimum": 0},
            },
            "required": ["sku", "nome"],
        },
    },
    {
        "name": "prever_compra",
        "description": (
            "Valida e prepara a criação de uma compra de peças ou de uma despesa. Compra de "
            "peças não recebe custo nesta etapa; custos entram pela cotação. Não grava nada."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "enum": ["parts", "expense"]},
                "fornecedor": {"type": "string"},
                "numero_pedido": {"type": "string"},
                "origem": {"type": "string"},
                "categoria_despesa": {"type": "string"},
                "valor_despesa": {"type": "number", "minimum": 0},
                "descricao_despesa": {"type": "string"},
                "pagamento": {"type": "string", "enum": ["cash", "installments", "entry"]},
                "parcelas": {"type": "integer", "minimum": 1, "maximum": 36},
                "primeiro_vencimento_dias": {"type": "integer", "minimum": 0},
                "observacoes": {"type": "string"},
                "itens": {
                    "type": "array",
                    "maxItems": 100,
                    "items": {
                        "type": "object",
                        "properties": {
                            "sku": {"type": "string"},
                            "descricao": {"type": "string"},
                            "quantidade": {"type": "number", "exclusiveMinimum": 0},
                            "unidade": {"type": "string"},
                            "custo_unitario": {"type": "number", "minimum": 0},
                        },
                        "required": ["descricao", "quantidade"],
                    },
                },
            },
            "required": ["tipo"],
        },
    },
    {
        "name": "prever_ajuste_estoque",
        "description": (
            "Valida e prepara um ajuste de estoque, mostrando saldo anterior e resultante. "
            "Não é recebimento de compra e não grava nada antes da confirmação."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "sku": {"type": "string"},
                "operacao": {"type": "string", "enum": ["entrada", "saida"]},
                "quantidade": {"type": "number", "exclusiveMinimum": 0},
                "motivo": {"type": "string"},
            },
            "required": ["operacao", "quantidade", "motivo"],
        },
    },
]

READ_TOOLS = {
    "buscar_produtos": lambda db, args, user: tool_reads.buscar_produtos(
        db,
        str(args.get("termo") or ""),
        int(args.get("limite") or 50),
        bool(args.get("abaixo_minimo")),
    ),
    "consultar_vendas": lambda db, args, user: tool_reads.consultar_vendas(
        db, str(args.get("identificador") or "")
    ),
    "listar_vendas": lambda db, args, user: tool_reads.listar_vendas(
        db,
        args.get("status_pedido") or None,
        args.get("status_envio") or None,
        bool(args.get("pendentes_envio")),
        int(args.get("limite") or 10),
    ),
    "investigar_fiscal": lambda db, args, user: tool_reads.investigar_fiscal(
        db, str(args.get("identificador") or "")
    ),
    "listar_compras": lambda db, args, user: tool_reads.listar_compras(
        db, args.get("busca") or None, args.get("status") or None
    ),
    "resumo_operacional": lambda db, args, user: tool_ops.resumo_operacional(db),
    "listar_contas_a_pagar": lambda db, args, user: tool_ops.listar_contas_a_pagar(
        db,
        bool(args.get("vencidas")),
        str(args.get("status") or "open"),
        int(args.get("limite") or 10),
    ),
    "buscar_clientes": lambda db, args, user: tool_ops.buscar_clientes(
        db, str(args.get("termo") or ""), int(args.get("limite") or 10)
    ),
    "movimentacoes_estoque": lambda db, args, user: tool_ops.movimentacoes_estoque(
        db, args.get("sku") or None, int(args.get("limite") or 15)
    ),
    "listar_erros_fiscais": lambda db, args, user: tool_ops.listar_erros_fiscais(
        db, int(args.get("limite") or 10)
    ),
    "detalhar_venda": lambda db, args, user: tool_ops.detalhar_venda(
        db, str(args.get("identificador") or "")
    ),
}

PREVIEW_TOOLS = {"prever_produto", "prever_compra", "prever_ajuste_estoque"}


def run_tool(
    db: Session,
    *,
    conversation: AssistantConversation,
    user: User,
    name: str,
    args: dict,
) -> dict:
    if name in READ_TOOLS:
        return READ_TOOLS[name](db, args, user)
    if name in PREVIEW_TOOLS:
        return actions.create_pending(
            db, conversation=conversation, user=user, tool_name=name, args=args
        )
    return {"erro": "Ferramenta não disponível."}


def safe_run(
    db: Session,
    *,
    conversation: AssistantConversation,
    user: User,
    name: str,
    args: dict,
) -> dict:
    try:
        return run_tool(
            db, conversation=conversation, user=user, name=name, args=args
        )
    except (ActionError, HTTPException) as error:
        detail = error.message if isinstance(error, ActionError) else str(error.detail)
        return {"erro": detail}
    except Exception:
        return {"erro": "Não foi possível concluir a consulta no ERP."}
