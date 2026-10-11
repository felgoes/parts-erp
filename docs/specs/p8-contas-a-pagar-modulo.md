# P8 — Contas a pagar como módulo

**Status:** concluído em 10/10/2026; validado em HML local e implantado em PRD no commit 2e5a0f7, com smoke checks públicos do site e ERP em HTTP 200
**Prioridade:** P8

## Objetivo

Transformar o título a pagar criado pela fase 1 da P7 em um módulo operacional: visão consolidada do passivo, baixa com pagamentos parciais, aging, conciliação e relatórios — sem quebrar as regras de cancelamento/estorno já entregues.

## Escopo herdado (decisão 5 da P7)

Despesa lançada e compra recebida geram título com fornecedor, valor, vencimento e vínculo ao documento de origem. O cancelamento encerra o título em vez de apagá-lo. A visão consolidada, os pagamentos parciais, o aging e a conciliação ficam neste módulo.

## O que foi entregue

- **Visão consolidada** em `Contas a pagar` (menu Análise): todos os títulos de compras e despesas, com fornecedor, origem (compra/despesa e número), valor, pago, saldo, vencimento, atraso e situação.
- **Resumo** com saldo em aberto, vencido, a vencer nos próximos dias (padrão 7, configurável na API) e pago no período, incluindo quantos pagamentos ainda estão sem conciliação.
- **Aging** por faixa: a vencer, 1–15, 16–30, 31–60, 61–90 e mais de 90 dias de atraso, com quantidade e saldo.
- **Baixa com pagamentos parciais**: cada pagamento tem valor, data, forma e observação; o título passa por em aberto → baixa parcial → pago conforme os pagamentos registrados, que são a fonte de verdade do valor pago.
- **Conciliação**: cada pagamento pode ser conciliado (confere com o comprovante/extrato) e a conciliação bloqueia a remoção do pagamento até ser desfeita.
- **Ajuste de vencimento** do título pela interface, com registro no histórico da compra.
- **Relatórios**: saldo por fornecedor (em aberto, vencido, pago no período) e pagamentos por mês, com período selecionável.
- **Exportação CSV** dos títulos filtrados (separador `;` e BOM, abre direto no Excel pt-BR).
- **Filtros**: busca livre (fornecedor, número da compra, pedido do fornecedor, categoria), fornecedor, situação e "somente vencidos".
- **Integração com a fase 1**: o botão de baixa no detalhe da compra registra um pagamento real, o cancelamento encerra o título com estorno e o histórico da compra recebe evento de cada movimento.

## Decisões de implementação

- **Conciliação** é a conferência do pagamento com o comprovante/extrato, registrada com autor e data; não há integração bancária neste ERP, então a classificação é manual e auditável.
- **Permissões**: leitura do módulo exige `finance:read`; registrar pagamento, conciliar e ajustar vencimento exigem `purchases:manage` (admin/manager), mantendo o perfil financeiro como leitura.
- **Datas de calendário** (vencimento e data do pagamento) são tratadas como data pura, sem deslocamento de fuso; a agregação por mês usa o dia armazenado.
- **Sem exclusão** de título: o caminho é encerrar pela fase 1 (cancelamento com estorno) e remover/estornar pagamentos não conciliados.

## Critérios de aceite verificados

1. Títulos de compras e despesas aparecem consolidados com fornecedor, origem, valor, pago e saldo. ✅
2. É possível registrar mais de um pagamento até quitar o título, com histórico de autor, data, forma e observação. ✅
3. Pagamento acima do saldo é recusado com a informação do saldo atual. ✅
4. Reenviar o mesmo pagamento (chave de idempotência) não duplica a baixa. ✅
5. Pagamento conciliado não pode ser removido enquanto a conciliação existir. ✅
6. Aging e resumo refletem os filtros aplicados e a data de vencimento. ✅
7. Filtro "somente vencidos" e busca por fornecedor funcionam. ✅
8. Relatórios por fornecedor e por mês usam o período de pagamentos selecionado. ✅
9. Exportação CSV lista os títulos filtrados com valor, pago, saldo e atraso. ✅
10. Cancelar a compra/despesa encerra o título com estorno, preservando o histórico. ✅

## Testes

- `backend/tests/test_payables.py`: baixa parcial e total, idempotência, recusa de excesso, conciliação e remoção, aging/resumo/filtros, relatório por fornecedor e mês, CSV e título encerrado.
- Frontend: 23 testes (inclui o aceite de valores decimais em texto nos campos monetários) e build de produção.

## Fora de escopo

- Integração bancária/OFX, conciliação automática e importação de extrato.
- Pagamentos com múltiplos títulos por recibo, adiantamentos a fornecedor e renegociação de dívida.
- Boletos, remessa/retorno bancário e emissão fiscal.
- Relatórios contábeis formais (DRE, balanço) e centro de custo.
