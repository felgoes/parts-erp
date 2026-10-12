# P5 — Taxa extra (taxa de pagamento) na cotação, na importação e na compra

**Status:** decidida em 12/10/2026; pronta para implementação.
**Prioridade:** alta — mexe em dinheiro (custo de aquisição e título a pagar).

## Objetivo

Registrar as taxas cobradas **por fora do valor das peças** — taxa de processamento de pagamento,
taxa de pagamento, juros de parcelamento — somando ao que foi realmente pago, entrando no custo de
aquisição das peças e no título a pagar. Hoje a compra fecha no total do pedido e a diferença entre
o pedido e o valor pago fica fora do ERP: o custo da peça nasce subestimado e o título nasce menor
do que a saída de caixa.

## Evidência

- Documento real de compra (AliExpress): `Order total BRL 310,34` · `Payment processing fee BRL 9,31`
  · `Amount paid BRL 319,65` — a taxa existe no papel e não tem onde ser lançada.
- Modelo atual: `PurchaseQuote` tem `freight_amount`, `tax_amount` e `discount_amount`; `PurchaseItem`
  tem `base_unit_cost`, `freight_amount`, `tax_amount`, `discount_amount` e `unit_cost`. **Não existe
  campo para taxa extra** (`backend/app/models/entities.py`, `backend/app/api/routes/purchases.py`).
- Perfis de reconhecimento (`backend/app/services/purchase_import.py`) reconhecem frete, desconto,
  imposto, total e valor pago, mas nenhum rótulo de taxa de pagamento.
- Risco no próprio reconhecedor: a lista genérica de rótulos de imposto inclui `"taxa"`, então um
  documento em português com "Taxa de pagamento R$ 9,31" pode ser lido como **imposto**.

## Decisões

1. **Nome na interface:** campo **"Taxas extras"**, com o texto de apoio "taxa de pagamento,
   processamento ou juros cobrados por fora do valor das peças".
2. **Taxa extra é acréscimo**, tratada como o frete: entra no total e é rateada entre as peças pelo
   método de rateio da cotação, compondo o custo unitário final (custo de aquisição).
3. **Fechamento da cotação:** `soma dos itens + frete + impostos + taxas extras − desconto = total`.
   Estende o fechamento já entregue no fluxo de importação (P0, commit `25a365e`); a tolerância
   continua R$ 0,01 por item.
4. **No documento importado, o total de referência é o valor efetivamente pago** (`Amount paid`/
   `total pago`) quando existir taxa reconhecida ou quando o valor pago for maior que o total do
   pedido. Sem taxa, total pago e total do pedido são o mesmo número.
5. **Reconhecimento:** novo grupo `extras` nos perfis: `payment processing fee`, `processing fee`,
   `payment fee`, `taxa de pagamento`, `taxa de processamento`, `taxa de processamento de pagamento`,
   `taxa de serviço`, `juros`, `juros de parcelamento`.
6. **O rótulo específico vence o genérico:** "taxa de pagamento" e "taxa de processamento" são
   buscados **antes** do rótulo genérico `taxa` usado para impostos, e o mesmo valor nunca é
   preenchido em dois campos. Em dúvida, o valor fica sinalizado para revisão humana.
7. **Sugestão revisável como fallback:** se nenhum rótulo de taxa for reconhecido, mas o valor pago
   do documento for maior que o total do pedido, a revisão sugere a diferença em "Taxas extras" com
   baixa confiança e o texto "diferença entre total do pedido e valor pago — confira". A sugestão
   nunca é aplicada sozinha: sem confirmação da pessoa, a soma não fecha e a confirmação é bloqueada.
8. **Onde o valor é digitado:** no formulário de cotação (compra de peças) e na revisão da
   importação. A compra digitada continua sem campo monetário — o valor entra só pela cotação, como
   já vale para frete, impostos e desconto.
9. **Onde o valor aparece:** revisão da importação (campo e fechamento), formulário e detalhe de
   cotação, composição de custo de cada peça (base, frete, impostos, **taxas extras**, desconto),
   resumo e lista de compras, título a pagar e relatórios financeiros.
10. **Título a pagar:** o valor devido é o da cotação vencedora, já com a taxa, e as parcelas seguem
    a condição de pagamento. Mudar a taxa depois da aprovação segue a regra vigente: a cotação
    escolhida é travada, registra-se nova cotação e o título em aberto é recalculado, preservando as
    parcelas já pagas.
11. **Campo opcional:** vazio significa "não informado" e não vira `R$ 0,00`; no cálculo, vazio vale
    zero. Usa a máscara de valores do ERP (somente inclusão, duas casas, `R$` intocável).
12. **Custo médio:** como a taxa entra no custo unitário final da peça, o recebimento continua
    atualizando o custo médio pelo valor final, sem cálculo novo.
13. **Despesa da empresa fica fora desta fase**: despesa não tem cotação nem rateio por peça.

## Casos de borda

- Documento sem taxa: campo vazio, total igual ao do pedido, comportamento atual preservado.
- Taxa reconhecida e total igual ao do pedido (taxa não somada): a soma não fecha e a confirmação é
  bloqueada com a diferença e a indicação de conferir valor pago e taxa.
- Valor pago menor que o total do pedido: sem sugestão automática; a revisão sinaliza a divergência e
  não fecha até a pessoa ajustar algum campo.
- Frete + impostos + taxas acima do total, ou desconto que deixe o custo de uma peça negativo:
  bloqueado com o motivo, sem salvar proposta impossível.
- Mesmo valor reconhecido como imposto e como taxa: não duplicar; manter em um campo e sinalizar.
- Taxa rateada com sobra de centavos: sobra no item de maior valor, como o frete, com a soma dos
  rateios exatamente igual à taxa informada.
- Compra sem cotação escolhida: não tem taxa, não tem título e a taxa não entra no custo.
- Valor com mais de duas casas: o campo sinaliza e bloqueia o salvamento, como qualquer valor do ERP.
- Cotação com taxa em compra já aprovada: cotação escolhida é travada; nova cotação corrige e o título
  em aberto é recalculado.
- Reenvio/duplo clique na confirmação da importação: a taxa não duplica (idempotência por
  `source_import_id`).

## Fora de escopo

- Taxa extra em despesa da empresa (decisão 13).
- Taxa extra em venda, fatura de venda ou recebível de marketplace.
- Antecipação, câmbio, IOF destacado, multa por atraso e juros de mora.
- Recalcular custo médio histórico de peças já recebidas antes desta entrega.
- Criar campo de valor na compra digitada, que segue sem valor até a cotação.

## Critérios de aceite

1. A revisão da importação mostra "Taxas extras" junto de frete, impostos e desconto, preenchido
   quando o documento traz a taxa e editável em qualquer caso.
2. O fechamento exibido é `itens + frete + impostos + taxas extras − desconto = total pago`, e a
   confirmação é bloqueada com a diferença na mensagem quando não fecha.
3. Documento com `Order total 310,34`, `Payment processing fee 9,31` e `Amount paid 319,65` cria a
   compra com total 319,65, título de 319,65 e custo unitário final de cada peça já com a taxa
   rateada.
4. O formulário de cotação aceita "Taxas extras", e a prévia de custo por peça e das parcelas do
   título considera a taxa.
5. O detalhe da compra mostra a taxa na composição de cada peça e no resumo, e a soma confere com o
   total da cotação e com o título.
6. O rateio da taxa segue o método da cotação, com a soma dos valores rateados exatamente igual à
   taxa informada e sobra de centavos no item de maior valor.
7. Campo vazio permanece vazio e é enviado como não informado, sem virar `R$ 0,00` e sem alterar os
   outros valores.
8. Cotação sem taxa continua igual (nenhuma regressão em frete, desconto, total bidirecional ou
   parcelas).
9. "Taxa de pagamento" em documento em português **não** é lançada como imposto: o rótulo genérico
   `taxa` deixa de capturar taxa de pagamento e nenhum valor é preenchido em dois campos.
10. Sem rótulo de taxa reconhecido e com valor pago maior que o total do pedido, a diferença aparece
    sugerida em "Taxas extras" com aviso de conferência, e a confirmação só passa após confirmação
    humana dos valores.
11. O recebimento de compra com taxa atualiza o custo médio e o valor do movimento de estoque pelo
    custo final com a taxa.
12. Taxa que deixe o custo de alguma peça negativo, ou frete + impostos + taxas acima do total,
    bloqueia o salvamento com o motivo.
13. Trocar a cotação de uma compra aprovada por outra com taxa diferente recalcula somente as
    parcelas em aberto do título e preserva as pagas.

## Verificação

- Testes de backend: validação da cotação com taxa, rateio (soma exata, sobra no maior item), custo
  unitário final, título com o valor pago, bloqueio de proposta impossível e ausência de duplicidade.
- Testes do reconhecedor: rótulos de taxa em inglês e português, prioridade sobre o rótulo genérico de
  imposto e a sugestão por diferença entre valor pago e total do pedido, com fixture anonimizada do
  layout recebido.
- HML: importar documento com taxa, conferir revisão, custo final por peça, título e recebimento;
  depois registrar cotação manual com taxa e conferir o mesmo caminho.
- Desktop e viewport móvel estreito, incluindo textos de apoio e mensagens de bloqueio.
