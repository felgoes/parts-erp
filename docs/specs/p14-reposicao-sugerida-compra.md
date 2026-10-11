# P14 — Reposição sugerida que gera o rascunho da compra

**Status:** decidida — decisões do PO fechadas em 11/10/2026, com uma decisão pendente do PO registrada abaixo; pendente de implementação (ver TASKS.md)
**Prioridade:** P2 da fila — alta

## Objetivo

Transformar o que o ERP já sabe — estoque mínimo, saldo, quantidade em pedido e giro de venda do período — em uma lista de reposição com quantidade sugerida por peça e valor estimado, e converter a seleção aprovada em rascunho(s) de compra por fornecedor contendo apenas peças e quantidades, sem valores, conforme a P9.

## História do usuário

Como comprador, quero abrir uma tela e ver o que está faltando, quanto vender nos próximos dias e quanto comprar de cada peça, para gerar o pedido ao fornecedor certo sem montar a lista de cabeça nem redigitar SKU e quantidade.

## Referência de mercado (ERP)

- **SAP (MM):** a reposição nasce de ponto de pedido, MRP e estoque de segurança; o resultado é requisição de compra sem preço, que depois vira pedido com preço do fornecedor vencedor.
- **TOTVS Protheus (Compras):** ponto de pedido e sugestão de compras geram a solicitação, que segue para cotação e pedido.
- **Omie, Bling e Tiny:** trazem relatórios de "produtos abaixo do mínimo" e "sugestão de compra" com base em giro e estoque mínimo; a lista vira pedido de compra.
- **Conclusão do benchmark:** sugestão de compra é capacidade básica de ERP de estoque, e no Parts ERP ela encaixa exatamente depois da P9, porque a compra agora nasce só com peças e quantidades.

## Fluxo proposto

1. Nova área **Reposição**, no menu Compras, usando o filtro de período compartilhado (`frontend/src/app/shared/period-filter.ts`) para o cálculo do giro.
2. Lista por peça com: SKU, nome, unidade, saldo, estoque mínimo, quantidade em pedido, vendido no período, média diária, autonomia do saldo em dias, quantidade sugerida, custo estimado e valor estimado.
3. Filtros: peças abaixo do mínimo (padrão), qualquer peça com sugestão maior que zero, fornecedor habitual, categoria e busca por SKU/nome.
4. Seleção de linhas e ação **Gerar rascunho de compra**: agrupa os itens selecionados por fornecedor habitual e cria um rascunho por fornecedor, com fornecedor definido, `needed_by` calculado pelo prazo padrão do fornecedor, peças e quantidades — sem cotação, sem valores e sem título a pagar.
5. Depois de gerar, a tela informa quantos rascunhos foram criados e quais itens ficaram de fora por não ter fornecedor definido, com atalho para a compra criada.
6. Ao voltar para a Reposição, os itens já incluídos em pedido aparecem na coluna "em pedido" e não são sugeridos de novo.

## Regras e decisões fechadas

1. **Fórmula da sugestão:** `necessidade = mínimo + consumo_previsto − (saldo + em pedido)`, com `consumo_previsto = média_diária × dias_de_cobertura`. Sugestão igual a zero ou negativa remove a linha da lista.
2. **Consumo** é a venda líquida do período: soma das quantidades de `MovementType.sale` menos cancelamentos e devoluções de cliente do mesmo período. Vendas ainda não sincronizadas do marketplace não contam, porque a base é o movimento de estoque do ERP.
3. **Dias de cobertura padrão 30**, ajustável na própria tela entre 7 e 180. *Decisão pendente do PO: número padrão definitivo (30, 45 ou 60 dias) e a possibilidade de configurar por fornecedor.* A implementação usa 30 enquanto a decisão não for tomada.
4. **Arredondamento:** peças são arredondadas para cima em unidades inteiras, e a sugestão nunca é menor que 1 quando a linha entra. Materiais com unidade fracionada são arredondados para cima com 3 casas.
5. **Peças sem estoque mínimo cadastrado** (`minimum_stock = 0`) não entram na sugestão; a tela mostra a contagem delas com atalho para o catálogo, para o lojista decidir se cadastra o mínimo.
6. **Peça sem venda no período entra** quando o saldo está abaixo do mínimo, com sugestão `mínimo − saldo − em pedido`.
7. **Em pedido** considera compras em `negotiating`, `approved`, `ordered` e `partially_received`, somando `quantidade − quantidade recebida` dos itens.
8. **Fornecedor habitual** é o fornecedor do recebimento mais recente daquela peça; sem histórico, o item fica "sem fornecedor" e o usuário escolhe na hora de gerar o rascunho.
9. **Custo estimado** usa o último custo de compra do item e, na sua falta, o `cost_price` do cadastro. É referência de orçamento, nunca valor de compra: o rascunho continua sem valores (P9).
10. **Um rascunho por fornecedor**, sempre sem cotação escolhida e sem título a pagar. Quando já existir rascunho aberto do mesmo fornecedor, a tela avisa antes de criar outro.
11. **Nada é aprovado automaticamente:** o rascunho segue o fluxo normal de cotação (P11), aprovação e condição de pagamento (P12).
12. **Unidade e rascunho seguem o cadastro:** a quantidade entra como um número, na unidade da peça, como em qualquer inclusão manual de peça na compra.

## Casos de borda

- Período sem nenhuma venda e saldo acima do mínimo: nenhuma linha.
- Peça abaixo do mínimo com saldo negativo (não deveria ocorrer): sugerir o mínimo cheio.
- Peça inativa não entra na sugestão; peça ativa sem preço de venda entra (reposição é sobre estoque, não sobre preço).
- Produto com vários anúncios ou vários canais: conta uma vez.
- Peça de almoxarifado (`stock_type = warehouse`) não entra nesta fase.
- Geração interrompida por erro em um fornecedor: os rascunhos já criados permanecem e a tela informa o que falhou, sem duplicar os já criados.
- Usuário sem permissão de compras: tela em modo somente leitura, sem o botão de gerar rascunho.

## Fora de escopo

- Previsão por sazonalidade, IA, curva ABC ou estoque de segurança por classe.
- Lote econômico de compra, desconto por volume e negociação por faixa de quantidade.
- Compra de materiais de almoxarifado e de despesas da empresa.
- Enviar cotação automaticamente a fornecedor (e-mail/WhatsApp) e comparar propostas.
- Alterar o cálculo de custo de aquisição, rateio da cotação (P11) e parcelas do título (P12).

## Critérios de aceite

1. A área Reposição lista peças abaixo do mínimo com saldo, mínimo, em pedido, vendido no período, autonomia e quantidade sugerida, respeitando o filtro de período compartilhado.
2. Peça com saldo 3, mínimo 10, em pedido 0 e consumo previsto 20 sugere 27; com em pedido 20 sugere 7; com sugestão zero não aparece.
3. Peça sem venda no período e abaixo do mínimo sugere `mínimo − saldo − em pedido`, no mínimo 1.
4. Peça com mínimo zero não aparece na lista, e a contagem delas é exibida com atalho para o catálogo.
5. Selecionar linhas de dois fornecedores e gerar a compra cria exatamente dois rascunhos, cada um com as peças e quantidades corretas do seu fornecedor.
6. O rascunho criado não tem cotação escolhida, nenhum campo de valor preenchido e nenhum título a pagar.
7. Itens sem fornecedor definido não são criados silenciosamente: a tela informa quais ficaram de fora.
8. Gerar a reposição duas vezes seguidas não duplica itens já em pedido, e a tela avisa sobre rascunho aberto do mesmo fornecedor.
9. Mudar os dias de cobertura na tela recalcula a sugestão e o valor estimado sem recarregar a página.
10. Usuário sem permissão de compras não vê a ação de gerar rascunho.
11. O rascunho criado aparece na lista de compras com o fornecedor definido e segue o fluxo normal de cotação, aprovação e recebimento.

## Verificação

- Teste de backend para o cálculo da sugestão (fórmula, arredondamento, em pedido, venda líquida do período, mínimo zero) e para a geração dos rascunhos por fornecedor.
- HML local: cadastrar peças com mínimo, registrar vendas e compras em aberto, conferir a lista, gerar os rascunhos e seguir o fluxo até a cotação.
- Conferir a tela em desktop e em viewport móvel estreito, com o filtro de período compartilhado.
