# P1 — Taxa extra (taxa de pagamento) na cotação, na importação e na compra

**Status:** decidida — decisão do PO fechada em 12/10/2026; pendente de implementação (ver TASKS.md)
**Prioridade:** alta — 2ª da fila

## Objetivo

Registrar as taxas cobradas **por fora do valor das peças** — taxa de processamento de pagamento, taxa de pagamento, juros de parcelamento — somando ao que foi realmente pago, entrando no custo de aquisição das peças e no título a pagar. Hoje a compra fecha no total do pedido e a diferença entre o pedido e o valor pago fica fora do ERP: o custo da peça nasce subestimado e o título nasce menor do que a saída de caixa.

## História do usuário

Como comprador, quero lançar a taxa de pagamento junto da compra, porque o fornecedor me cobra o valor das peças **mais** a taxa e esse dinheiro saiu do caixa: o custo real da peça e o título a pagar precisam incluir essa taxa.

## Evidência

- Documento de compra (AliExpress): `Order total BRL 310,34` · `Payment processing fee BRL 9,31` · `Amount paid BRL 319,65`.
- O modelo atual tem `PurchaseQuote` com `freight_amount`, `tax_amount` e `discount_amount`, e `PurchaseItem` com `base_unit_cost`, `freight_amount`, `tax_amount`, `discount_amount` e `unit_cost` — **não existe campo para taxa extra** (`backend/app/models/entities.py`, `backend/app/api/routes/purchases.py`).
- Os perfis de reconhecimento (`backend/app/services/purchase_import.py`) reconhecem frete, desconto, imposto e valor pago, mas nenhum rótulo de taxa de pagamento.
- Risco verificado no próprio reconhecedor: a lista genérica de rótulos de imposto inclui `"taxa"`, então um documento em português com "Taxa de pagamento R$ 9,31" pode ser lido como **imposto**, inflando o campo errado.

## Regras e decisões fechadas

1. **Nome na interface:** campo **"Taxas extras"**, com o texto de apoio "taxa de pagamento, processamento ou juros cobrados por fora do valor das peças".
2. **Taxa extra é acréscimo**, tratada como o frete: entra no total e é rateada entre as peças pelo método de rateio da cotação, compondo o custo unitário final de cada peça (custo de aquisição).
3. **Fechamento da cotação:** `soma dos itens + frete + impostos + taxas extras − desconto = total`. Esta regra estende o fechamento definido na P0; a tolerância continua R$ 0,01 por item.
4. **No documento importado, o total de referência é o valor efetivamente pago** (`Amount paid`/`total pago`) quando existir taxa reconhecida ou quando o valor pago for maior que o total do pedido. Sem taxa, total pago e total do pedido são o mesmo número.
5. **Reconhecimento:** novo grupo de rótulos `extras` nos perfis: `payment processing fee`, `processing fee`, `payment fee`, `taxa de pagamento`, `taxa de processamento`, `taxa de processamento de pagamento`, `taxa de serviço`, `juros de parcelamento`, `juros`.
6. **O rótulo específico vence o genérico:** a busca por "taxa de pagamento" e "taxa de processamento" acontece **antes** do rótulo genérico `taxa` usado para impostos, e o mesmo valor nunca é preenchido em dois campos. Quando houver dúvida, o valor é sinalizado para revisão humana em vez de escolhido em silêncio.
7. **Sugestão revisável como fallback:** se nenhum rótulo de taxa for reconhecido, mas o valor pago do documento for maior que o total do pedido, a revisão sugere a diferença em "Taxas extras" com baixa confiança e o texto "diferença entre total do pedido e valor pago — confira". A sugestão nunca é aplicada sozinha: sem confirmação da pessoa, a soma não fecha e a confirmação fica bloqueada.
8. **Onde o valor é digitado:** no **formulário de cotação** (compra de peças) e na **revisão da importação**. A compra digitada continua sem campo monetário, e o valor entra apenas pela cotação, como já vale para frete, impostos e desconto.
9. **Onde o valor aparece:** revisão da importação (campo e fechamento), formulário e detalhe de cotação, composição de custo de cada peça (base, frete, impostos, **taxas extras**, desconto) e resumo da compra, lista de compras, título a pagar e relatórios financeiros.
10. **Título a pagar:** o valor devido é o da cotação vencedora, já com a taxa, e as parcelas continuam derivadas da condição de pagamento. Mudar a taxa depois da aprovação segue a regra vigente: a cotação escolhida é travada, registra-se nova cotação e o título em aberto é recalculado, preservando parcelas já pagas.
11. **Campo opcional:** vazio significa "não informado" e não vira `R$ 0,00`; no cálculo, vazio vale zero. O campo usa a máscara de valores do ERP (somente inclusão, duas casas, `R$` intocável).
12. **Custo médio:** como a taxa entra no custo unitário final da peça, o recebimento continua atualizando o custo médio pelo valor final, sem cálculo novo.
13. **Fora desta fase:** despesa da empresa (aluguel, serviços e outras sem cotação) não recebe taxa extra nesta entrega, porque a despesa não tem cotação nem rateio por peça.

## Casos de borda

- Documento sem taxa: campo vazio, total igual ao do pedido e nenhuma mudança em relação ao comportamento atual.
- Documento com taxa reconhecida e total igual ao do pedido (taxa não somada): o fechamento não fecha e a confirmação é bloqueada com a diferença e a indicação de conferir valor pago e taxa.
- Valor pago menor que o total do pedido (desconto aplicado no pagamento, câmbio ou estorno): sem sugestão automática; a revisão sinaliza a divergência e não fecha até a pessoa ajustar algum campo.
- Taxa, frete e impostos somados acima do total: bloqueado com o motivo, sem salvar proposta impossível.
- Desconto maior que itens + frete + impostos + taxas: bloqueia por deixar o custo de alguma peça negativo.
- Mesmo valor reconhecido como imposto e como taxa extra: não duplicar; manter em um campo e sinalizar a linha para revisão.
- Taxa rateada com sobra de centavos: a sobra vai para o item de maior valor, igual ao frete, e a soma dos rateios é exatamente a taxa informada.
- Compra sem cotação escolhida: não tem taxa, não tem título e o valor não entra no custo (a taxa só existe dentro de uma cotação).
- Taxa informada em decimal com mais de duas casas: o campo sinaliza e bloqueia o salvamento, como qualquer valor do ERP.
- Cotação com taxa em compra já aprovada: a cotação escolhida é travada; nova cotação com a taxa corrigida substitui e o título em aberto é recalculado.
- Reenvio/duplo clique na confirmação da importação: a taxa não duplica (idempotência por `source_import_id`).

## Fora de escopo

- Taxa extra em despesa da empresa (regra 13).
- Taxa extra em venda, em fatura de venda ou em recebível de marketplace.
- Antecipação, câmbio, IOF destacado, juros de mora e multa por atraso.
- Recalcular custo médio histórico de peças já recebidas antes desta entrega.
- Criar campo de valor na compra digitada, que segue sem valor até a cotação.

## Critérios de aceite

1. A revisão da importação mostra o campo "Taxas extras" junto de frete, impostos e desconto, já preenchido quando o documento traz a taxa e editável em qualquer caso.
2. O fechamento mostrado na revisão é `itens + frete + impostos + taxas extras − desconto = total pago`, e a confirmação é bloqueada com a diferença na mensagem quando não fecha.
3. Documento com `Order total 310,34`, `Payment processing fee 9,31` e `Amount paid 319,65` cria a compra com total 319,65, título a pagar de 319,65 e custo unitário final de cada peça já com a taxa rateada.
4. O formulário de cotação aceita "Taxas extras", e a prévia de custo por peça e das parcelas do título considera a taxa.
5. O detalhe da compra mostra a taxa na composição de cada peça e no resumo, e a soma das composições confere com o total da cotação e com o título.
6. O rateio da taxa segue o método da cotação e a soma dos valores rateados é exatamente a taxa informada, com a sobra de centavos no item de maior valor.
7. Campo vazio permanece vazio e é enviado como não informado, sem virar `R$ 0,00` e sem alterar os outros valores.
8. Cotação sem taxa continua se comportando exatamente como hoje (nenhuma regressão em frete, desconto, total bidirecional ou parcelas).
9. "Taxa de pagamento" em documento em português **não** é lançada como imposto; o rótulo genérico `taxa` deixa de capturar taxa de pagamento, e nenhum valor é preenchido em dois campos.
10. Quando nenhum rótulo de taxa é reconhecido e o valor pago é maior que o total do pedido, a diferença aparece sugerida em "Taxas extras" com aviso de conferência, e a confirmação só passa depois de a pessoa confirmar os valores.
11. O recebimento de compra com taxa atualiza o custo médio e o valor do movimento de estoque pelo custo final com a taxa.
12. Taxa que deixe o custo de alguma peça negativo, ou frete + impostos + taxas acima do total, bloqueia o salvamento com o motivo explicando qual valor conferir.
13. Trocar a cotação de uma compra aprovada por outra com taxa diferente recalcula somente as parcelas em aberto do título e preserva as já pagas.

## Verificação

- Testes de backend: validação da cotação com taxas extras, rateio (soma exata, sobra no maior item), custo unitário final, título com o valor pago, bloqueio de proposta impossível e ausência de duplicidade ao reler o documento.
- Testes do reconhecedor: rótulos de taxa de pagamento em inglês e português, prioridade sobre o rótulo genérico de imposto, e a sugestão por diferença entre valor pago e total do pedido com fixture anonimizada do layout recebido.
- HML local: importar documento com taxa, conferir revisão, custo final por peça, título no contas a pagar e recebimento; depois registrar uma cotação manual com taxa e conferir o mesmo caminho.
- Conferir em desktop e em viewport móvel estreito, incluindo os textos de apoio e as mensagens de bloqueio.
