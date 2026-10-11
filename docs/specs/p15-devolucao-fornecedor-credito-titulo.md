# P15 — Devolução pontual ao fornecedor com crédito no título a pagar

**Status:** decidida — decisões do PO fechadas em 11/10/2026; pendente de implementação (ver TASKS.md)
**Prioridade:** P4 da fila — média

## Objetivo

Permitir devolver ao fornecedor peças recebidas com defeito, peça errada, avaria ou excedente **sem cancelar a compra inteira**, dando baixa de estoque documentada e reduzindo o que ainda está em aberto no título a pagar pelo valor devolvido. Hoje o único caminho é cancelar a compra toda, o que encerra o título, perde o registro dos itens bons e obriga a refazer o pedido do que estava certo.

## História do usuário

Como responsável pela compra, quero devolver só as peças com problema e receber o desconto correspondente no título a pagar, mantendo o resto do pedido, o estoque e o histórico intactos.

## Situação verificada no código (commit ffff8a2)

- A devolução ao fornecedor já existe **apenas** dentro do cancelamento da compra: `_register_returns` (`backend/app/api/routes/purchases.py`) dá baixa no estoque, exige produto vinculado, recusa devolver mais do que foi recebido e grava `returned_quantity` no item — mas só é alcançável pela resolução "devolver o material recebido" do cancelamento, que encerra o título.
- `_owed_value` devolve o total da cotação vencedora para compra não encerrada, ou seja, **a devolução parcial não reduz o título** fora do cancelamento; só a compra encerrada (`closed`) passa a valer o recebido líquido de devoluções (`_received_value`).
- O modelo já tem `PurchaseItem.returned_quantity` e o evento `item_returned` no histórico da compra.
- O contas a pagar (P8) baixa por parcela, e a P12 recalcula apenas as parcelas em aberto quando o valor do título muda (`apply_payment_condition` preserva as parcelas com pagamento).
- `MovementType` não tem tipo próprio de devolução ao fornecedor; o cancelamento usa `cancellation`.

## Escopo

- Ação **Devolver ao fornecedor** no detalhe da compra, disponível quando existir quantidade recebida ainda não devolvida, para compras de peças e para materiais de almoxarifado de despesa.
- Formulário por item: quantidade a devolver, motivo estruturado, número do documento/RMA (opcional) e observação (opcional).
- Novos estados e registros: item com quantidade devolvida acumulada, evento na compra com autor, data/hora, quantidade, motivo e valor, e crédito registrado no histórico do título.
- Financeiro: o valor devido da compra passa a descontar o valor devolvido; parcelas em aberto são recalculadas mantendo as já pagas (regra da P12); sobra de crédito além do saldo em aberto vira "crédito a compensar com o fornecedor", registrado na compra e visível no contas a pagar.
- Tipo de movimento próprio: `purchase_return`, com migração Alembic para o enum do PostgreSQL (`ALTER TYPE ... ADD VALUE`), para não misturar devolução ao fornecedor com cancelamento de venda nos relatórios.

## Regras e decisões fechadas

1. **Motivo obrigatório**, escolhido de uma lista fixa: defeito, peça errada enviada, avaria no transporte, excedente, outro (com observação obrigatória quando for "outro").
2. **Não se devolve o que não foi recebido:** a quantidade é limitada a `recebido − já devolvido` e a devolução exige produto vinculado, como no fluxo atual.
3. **O estoque precisa ter a peça:** a baixa usa a regra atual de saldo e é recusada com mensagem clara quando o saldo atual não permite (peça vendida ou já devolvida); nunca deixa saldo negativo.
4. **Valor do crédito** = quantidade devolvida × custo unitário do item na compra. Quando o item estiver sem custo apurado (compra sem cotação escolhida e sem recebimento valorizado), a devolução é bloqueada com a mensagem "registre o custo da compra antes de devolver".
5. **O custo médio do produto não é recalculado** pela devolução: o movimento é valorizado pelo custo do item, e o custo médio permanece o que era.
6. **O título é reduzido, não apagado:** valor devido = valor acordado − valor devolvido; parcelas já pagas nunca são alteradas; as parcelas em aberto são redistribuídas pela mesma condição de pagamento (P12).
7. **Parcela paga não se altera e o título nunca fica com pago maior que o devido:** o valor devido nunca cai abaixo do total já pago; o excedente sai do título e é registrado como **crédito a compensar com o fornecedor**, exibido no detalhe da compra e no contas a pagar.
8. **A devolução não cancela a compra**, não altera a cotação escolhida, não muda a quantidade recebida e não devolve o saldo pendente do pedido.
9. **Devolução e cancelamento convivem:** o cancelamento com devolução do material recebido continua funcionando como hoje para o caso de cancelar o pedido inteiro.
10. **Rastreabilidade:** compra, item, quantidade, motivo, documento, valor, autor e data/hora ficam no histórico da compra e do título; a devolução é idempotente por chave (compra, item, quantidade acumulada) e reenvio não duplica baixa nem crédito.
11. **Estorno da devolução** permitido enquanto o título estiver em aberto e sem pagamento posterior ao abatimento: gera entrada compensatória no estoque com motivo "Estorno de devolução ao fornecedor · compra NNN", restaura o valor do título e fica auditado. Depois de o título ser quitado ou pago, a devolução não pode ser estornada.
12. **Permissão:** registrar e estornar devolução exige a permissão de gestão de compras (`purchases:manage`), a mesma usada para cancelar; a leitura segue as permissões atuais da compra e do contas a pagar.

## Casos de borda

- Devolução parcial repetida do mesmo item: soma o acumulado e nunca passa do recebido.
- Devolução de todos os itens recebidos de uma compra: permitida; a compra continua existindo com o que não foi devolvido e o título zera o aberto.
- Compra encerrada (`closed`) com material recebido: devolução permitida; compra cancelada ou rascunho: bloqueada com explicação.
- Título já quitado: devolução permitida para o estoque; o valor integral vira crédito a compensar.
- Devolução em compra de despesa com material de almoxarifado: permitida, com a mesma regra de estoque e de crédito.
- Peça já vendida no período: bloqueio por falta de saldo, com a mensagem do motivo.
- Quantidade fracionada conforme a unidade do item: aceita até 3 casas, respeitando o limite do recebido.
- Item sem observação em divergência grande: a observação continua opcional nesta fase, mas fica registrada quando informada.

## Fora de escopo

- Compensar o crédito a compensar em compra futura, abater em outro título ou emitir devolução de dinheiro ao lojista.
- Emitir nota fiscal de devolução, transporte reverso e integração com o fornecedor.
- Devolução de venda de cliente (pós-venda do marketplace), que já tem fluxo próprio e continua separada.
- Alterar o cancelamento de compra entregue na P7 e o cálculo de rateio da cotação (P11).
- Recálculo do custo médio histórico do produto e reavaliação de estoque.

## Critérios de aceite

1. O detalhe de uma compra com itens recebidos mostra a ação "Devolver ao fornecedor" com quantidade máxima devolvível igual a recebido menos já devolvido.
2. Registrar a devolução de 2 unidades de um item de R$ 50,00 dá baixa de 2 unidades no estoque com motivo "Devolução ao fornecedor · compra NNN" e crédito de R$ 100,00.
3. O título da compra cai de R$ 300,00 para R$ 200,00, com as parcelas em aberto redistribuídas e as parcelas já pagas intactas.
4. Devolver com o título já quitado não deixa saldo negativo e registra R$ 100,00 como crédito a compensar, visível na compra e no contas a pagar.
5. Tentar devolver mais do que foi recebido é recusado com a quantidade disponível na mensagem.
6. Tentar devolver item cujo estoque atual não cobre a quantidade é recusado com mensagem explicando o saldo.
7. Vender, cancelar venda e receber compra continuam funcionando e o saldo final do estoque fecha com as devoluções.
8. A devolução não altera a quantidade recebida, a cotação escolhida, o status da compra nem o custo médio do produto.
9. Reenviar a mesma devolução não duplica baixa de estoque, evento nem crédito.
10. O histórico da compra e o do título mostram quantidade, valor, motivo, autor e data/hora, com as datas em `America/Sao_Paulo` (`pt-BR`) e persistência em UTC.
11. Estornar uma devolução com o título ainda em aberto devolve as peças ao estoque e restaura o valor devido; com pagamento posterior, o estorno é bloqueado com explicação.
12. Compra de peças sem cotação escolhida e sem custo apurado bloqueia a devolução com a mensagem definida na decisão 4.

## Verificação

- Testes de backend em `backend/tests/test_purchases.py` (ou arquivo novo `test_supplier_returns.py`): limites de quantidade, saldo insuficiente, redução do título com parcela paga, crédito a compensar, idempotência e estorno.
- Migração Alembic aplicada em banco limpo e em banco com dados existentes, conferindo o novo valor de `MovementType` no enum do PostgreSQL.
- HML local: compra de três peças, aprovação, recebimento, devolução parcial de uma peça com defeito, conferência do estoque, do título e do crédito; depois conferir a tela em desktop e mobile.
