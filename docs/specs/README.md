# Especificações — Parts ERP

As specs descrevem comportamento e critérios de aceite de cada item. A lista oficial do que está pendente ou em andamento é o `TASKS.md` do workspace do projeto; concluída a tarefa, o histórico fica aqui (linha `Status:`) e no `RELEASE_NOTES.md`.

1. [P0 — Receber itens de compras no almoxarifado](p0-recebimento-estoque-compras.md)
2. [P1 — Máscara e precisão para valores em reais](p1-mascara-valores-moeda.md)
3. [P2 — Notas de atualização no GitHub](p2-release-notes-github.md)
4. [P3 — Reconhecimento de campos por plataforma](p3-reconhecimento-documentos-plataformas.md)
5. [P4 — Remover referências públicas à infraestrutura](p4-generalizar-referencias-publicas-infra.md)
6. [P5 — Visualização dos valores por item na compra](p5-visual-valores-itens-compra.md)
7. [P6 — Vincular itens importados aos produtos do estoque](p6-vincular-itens-importados-a-produtos.md)
8. [P7 — Simplificar o pedido de compra e permitir exclusão segura](p7-simplificar-pedido-compra-exclusao.md)
9. [P8 — Contas a pagar como módulo](p8-contas-a-pagar-modulo.md)
10. [P9 — Compra pede peças e quantidades; valores somente nas cotações](p9-compra-valores-somente-em-cotacoes.md)
11. [P10 — Máscara de valores forte, somente inclusão](p10-mascara-valores-somente-inclusao.md)
12. [P11 — Cotação com total e custo unitário em tempo real](p11-cotacao-total-unitario-tempo-real.md)
13. [P12 — Condição de pagamento da cotação gera as parcelas do título a pagar](p12-condicao-pagamento-parcelas-titulo.md)
14. [P13 — Estoque publicado coerente em cada canal](p13-estoque-publicado-canais.md)
15. [P14 — Reposição sugerida que gera o rascunho da compra](p14-reposicao-sugerida-compra.md)
16. [P15 — Devolução pontual ao fornecedor com crédito no título a pagar](p15-devolucao-fornecedor-credito-titulo.md)
17. [P16 — Catálogo público com disponibilidade e preço do anúncio](p16-catalogo-publico-disponibilidade-preco.md)
18. [P17 — Contagem de estoque com ajuste auditado](p17-contagem-estoque-sessao.md)
19. [P18 — Compra importada entra com a cotação do documento aceita e o pedido registrado](p18-compra-importada-cotacao-aceita.md)

## Fila priorizada

Ordem de execução definida em 11 de outubro de 2026, com a prioridade de cada item na linha `Status:` da própria spec:

| Ordem | Spec | Prioridade | Tema |
| --- | --- | --- | --- |
| 1ª | [P18](p18-compra-importada-cotacao-aceita.md) | alta | Compra importada entra com a cotação aceita e o pedido registrado |
| 2ª | [P13](p13-estoque-publicado-canais.md) | alta | Estoque publicado igual ao saldo em todos os canais |
| 3ª | [P14](p14-reposicao-sugerida-compra.md) | alta | Sugestão de reposição que gera o rascunho da compra |
| 4ª | [P15](p15-devolucao-fornecedor-credito-titulo.md) | média | Devolução ao fornecedor com crédito no título |
| 5ª | [P16](p16-catalogo-publico-disponibilidade-preco.md) | média | Disponibilidade e preço do anúncio no catálogo público |
| 6ª | [P17](p17-contagem-estoque-sessao.md) | baixa | Contagem de estoque com ajuste auditado |

Primeira tarefa da fila: **P18 — Compra importada entra com a cotação do documento aceita e o pedido registrado**. O `TASKS.md` é a lista oficial do que está pendente.
