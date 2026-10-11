# Lista de tarefas — Parts ERP

## Pendentes

- [ ] [P0] Compra importada entra com a cotação do documento aceita e o pedido registrado.
  Confirmar a importação hoje cria a compra "em negociação" com os valores lidos do papel nos itens, mas sem nenhuma cotação: o pedido não pode ser enviado, o recebimento fica bloqueado e o título não aparece no contas a pagar, obrigando o comprador a cadastrar uma cotação de mentira só para destravar o fluxo. A entrega registra a cotação do documento já aceita, cria o título a pagar com a condição padrão e registra o pedido na mesma transação, deixando a compra pronta para receber, com a revisão mostrando o custo final por peça e o fechamento do total.
  Spec: docs/specs/p0-compra-importada-cotacao-aceita.md

## Concluídas

## Encerradas sem implementação

## Fila solicitada

---

Fila em 11 de outubro de 2026: **P0 é a única tarefa pendente e a primeira da fila** (prioridade alta).
As specs anteriores (P0 a P17 do índice antigo) foram removidas a pedido do PO em 11/10/2026 e permanecem no histórico do Git e no `RELEASE_NOTES.md`.
