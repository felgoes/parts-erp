# P13 — Excluir pedido de compra pelos três pontos, com os registros ligados

**Status:** decidida — decisões do PO fechadas em 10/10/2026; pronta para implementação
**Prioridade:** P2

## Contexto

Hoje o menu de três pontos da lista de compras oferece apenas "Copiar". A exclusão existe, mas está fora do menu: no detalhe do pedido como "Excluir rascunho" e na seleção em lote da lista. E o sistema só apaga compra em negociação, sem cotação escolhida, sem pedido enviado, sem recebimento e sem título a pagar — qualquer um desses efeitos faz o servidor recusar a exclusão.

O resultado prático é uma compra que não sai da lista: um pedido criado por engano, uma compra de teste, uma importação repetida ou um pedido que avançou de etapa ficam presos sem caminho de correção pela tela. O usuário descobre o bloqueio abrindo o registro, e o menu que deveria concentrar as ações do pedido não tem a ação mais procurada.

Os registros que hoje dependem de uma compra são: itens, cotações, anexos, histórico de eventos do pedido, movimentação de estoque gerada no recebimento, título a pagar (com parcelas e pagamentos) e o vínculo de um estudo de mercado que aponta para a compra.

## Objetivo

Permitir excluir um pedido de compra direto no menu de três pontos, apagando junto os registros que nasceram dele, sem deixar estoque, financeiro ou histórico inconsistentes — e, quando houver efeito que não pode ser apagado (pagamento ao fornecedor ou mercadoria já consumida do estoque), bloquear explicando o motivo e indicando o caminho correto.

## Decisões de negócio (fechadas)

1. **A exclusão apaga a compra e os registros filhos.** Itens, cotações, anexos, eventos do histórico e título a pagar com parcelas e pagamentos saem junto com o pedido.
   - Por quê: "os registros que se relacionam" são os que nasceram da compra. Filho órfão ou registro bloqueando a exclusão é exatamente a dor atual.
   - Alternativa descartada: manter os filhos no banco marcados como removidos — complica toda consulta e não entrega o que o usuário pediu.
2. **Estoque recebido volta por movimento compensatório, não apagando o histórico de movimentações.** O saldo do produto retorna ao valor anterior e o estorno fica registrado na trilha de estoque.
   - Por quê: o saldo precisa voltar a ser o correto e a movimentação original precisa continuar auditável, o mesmo princípio já adotado na P7 para cancelamento e devolução.
   - Alternativa descartada: apagar as movimentações de estoque originais — apaga a prova do que entrou e saiu.
3. **Se o estorno deixar o saldo negativo, a exclusão é bloqueada.** Quando a peça recebida já saiu do estoque, a exclusão para com a mesma mensagem de estoque insuficiente que o ERP já usa, apontando a peça e o saldo disponível, e nada é apagado.
   - Por quê: a mercadoria já foi consumida; forçar o estorno deixaria o estoque negativo e mascararia uma venda real.
   - Alternativa descartada: permitir saldo negativo — criaria dado impossível e esconderia a divergência.
4. **Pagamento registrado no título bloqueia a exclusão.** Se o título a pagar já tem qualquer pagamento, a exclusão é recusada com explicação e o caminho oferecido é cancelar a compra com estorno, preservando o registro financeiro.
   - Por quê: pagamento ao fornecedor é fato de caixa; apagar a linha apagaria a saída de dinheiro e deixaria o caixa sem lastro.
   - Alternativa descartada: apagar título e pagamentos junto com a compra — destrói o registro de dinheiro que já saiu.
5. **A trilha de auditoria permanece.** Toda exclusão grava registro imutável com número, fornecedor, itens, valor total, autor, data/hora e um resumo do que foi removido junto (recebimento estornado, título apagado).
   - Por quê: a P7 já decidiu que exclusão gera auditoria imutável; apagar mais registros exige mais rastro, não menos.
   - Alternativa descartada: exclusão silenciosa, sem rastro.
6. **Só admin e gerente excluem** (permissão de gestão de compras, como já vale hoje). Operador continua lendo e recebendo.
   - Por quê: apagar compra com recebimento e financeiro é ato de gestão, não de operação de balcão.
   - Alternativa descartada: liberar para qualquer usuário — sem controle sobre o estoque e o passivo.
7. **A exclusão com efeitos é feita um registro por vez**, pelo menu de três pontos e pelo detalhe. A ação em lote da lista continua restrita a rascunhos sem efeitos.
   - Por quê: cascata em vários registros, com estorno de estoque, é fácil de virar acidente; uma compra por vez, com a confirmação mostrando os efeitos, é o mínimo seguro.
   - Alternativa descartada: estender a exclusão em lote para compras com recebimento e título.
8. **Antes de executar, a confirmação mostra o que será perdido**: número, fornecedor, valor total e a lista de efeitos — quantidade de itens, cotações e anexos, recebimento com peças que voltarão ao estoque e título a pagar com valor que será apagado.
   - Por quê: quem exclui precisa saber que o estoque volta e que o título desaparece, e não apenas responder "tem certeza?".
   - Alternativa descartada: confirmação genérica só com o número do pedido.
9. **O estudo de mercado vinculado é preservado e apenas desvinculado.** A compra apagada não pode ser motivo para perder uma pesquisa de preço.
   - Por quê: o estudo é registro independente; o vínculo é acessório.
   - Alternativa descartada: apagar o estudo junto — destruiria trabalho de pesquisa sem relação com o erro corrigido.

## Escopo

- Item "Excluir compra" no menu de três pontos de cada linha da lista de compras.
- Mesma ação no detalhe do pedido, substituindo o rótulo "Excluir rascunho".
- Exclusão em cascata dos registros filhos: itens, cotações, anexos (inclusive o arquivo armazenado), eventos do histórico do pedido e título a pagar com parcelas e pagamentos.
- Estorno de estoque por movimento compensatório quando houver recebimento, com bloqueio e explicação quando o saldo não permitir.
- Bloqueio com explicação e caminho alternativo quando houver pagamento registrado no título.
- Desvinculação do estudo de mercado que aponta para a compra.
- Confirmação em português listando os efeitos da exclusão, com valores em reais e datas no padrão do ERP.
- Registro de auditoria da exclusão com resumo do que foi removido junto.
- Rótulos coerentes entre menu, detalhe e ação em lote.

## Critérios de aceite

1. Cada linha da lista de compras tem a ação "Excluir compra" no menu de três pontos.
2. Compra em negociação sem efeitos: excluída pelo menu, desaparece da lista e deixa registro de auditoria.
3. Compra com cotação escolhida, pedido enviado, recebimento ou título a pagar é excluída pelo menu junto com os filhos, desde que não haja pagamento registrado e o estoque permita o estorno.
4. Exclusão de compra com recebimento devolve o saldo anterior dos produtos e registra o estorno como movimentação de estoque rastreável; as movimentações originais continuam existindo.
5. Quando o estorno deixaria o saldo negativo, a exclusão é bloqueada com mensagem apontando a peça e o saldo disponível, e nenhum registro é apagado.
6. Título com pagamento registrado bloqueia a exclusão com mensagem clara, sem apagar nada, e a compra continua na lista.
7. A confirmação exibe número, fornecedor, valor total e os efeitos: itens, cotações, anexos, recebimento (com quantidade) e título a pagar (com valor).
8. Toda exclusão gera auditoria imutável com número, fornecedor, itens, valor total, autor, data/hora e resumo do que foi removido junto.
9. Duplo clique, repetição ou reenvio não exclui duas vezes nem duplica estorno de estoque.
10. Estudo de mercado vinculado continua existindo e apenas perde o vínculo; nenhum registro de outro módulo aponta para uma compra apagada.
11. Anexos excluídos saem também do armazenamento, sem arquivo órfão.
12. A ação em lote da lista continua restrita a rascunhos sem efeitos, com rótulo coerente com a ação individual.
13. Valores exibidos em reais com duas casas e datas de calendário sem deslocamento de dia, exibidas em America/Sao_Paulo.

## Fora de escopo

- Exclusão em lote de compras com recebimento ou título a pagar.
- Excluir produtos, fornecedores ou títulos a pagar por conta própria.
- Estorno financeiro de dinheiro já pago ao fornecedor; nesse caso a spec só bloqueia e orienta.
- Reescrita, migração ou limpeza de compras antigas já lançadas.
- Exclusão automática por tempo, retenção ou rotina de limpeza de dados.

## Dependências e riscos

- Depende das estruturas atuais de compras, título a pagar (P8) e movimentação de estoque; não abre módulo novo.
- Risco: cascata em compra recebida mexe no estoque. Mitigado pelo movimento compensatório, pelo bloqueio de saldo negativo e pela confirmação explícita.
- Risco: perda de rastro. Mitigado pela auditoria da exclusão e pela manutenção da trilha de movimentações.
- Risco: o vínculo do estudo de mercado hoje não tem regra de exclusão e barraria o apagamento. Deve ser desvinculado antes.
- Verificação: varrer os vínculos existentes com a compra antes de fechar a implementação, porque módulos novos podem passar a apontar para ela; nenhuma referência pode sobrar apontando para compra apagada.

## Referências de mercado

| Prática consolidada | Referência | Decisão para o Parts ERP |
| --- | --- | --- |
| Documento confirmado é cancelado, não apagado; rascunho pode ser excluído | [Odoo](https://www.odoo.com/documentation/saas-15.1/applications/finance/accounting/payables/supplier_bills/manage.html), [Dynamics 365](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/purchase-order-approval-confirmation) | Adotado em parte: a exclusão avança para documentos já emitidos, mas para onde parou efeito irreversível — pagamento ou estoque já consumido |
| Reversão por documento/movimento compensatório, preservando o histórico | [SAP Business One](https://help.sap.com/docs/SAP_BUSINESS_ONE/68a2e87fb29941b5bf959a184d9c6727/450a572b37ca1f2ce10000000a1553f6.html) | Adotado: estoque volta por movimento compensatório rastreável |
| Ações destrutivas exigem autorização e rastro de auditoria | Odoo, Dynamics 365, NetSuite | Adotado: exclusão restrita a admin/gerente, com auditoria imutável |

## Faseamento

Entrega única, sem fases: menu, cascata, estorno de estoque, bloqueios, auditoria e confirmação detalhada formam um comportamento só, e entregar pela metade deixaria a exclusão pela metade. Se a implementação precisar ser dividida, a primeira entrega é a cascata dos registros filhos com título em aberto e sem recebimento (itens, cotações, anexos, eventos, título sem pagamento) e o estorno de estoque entra na parte seguinte.
