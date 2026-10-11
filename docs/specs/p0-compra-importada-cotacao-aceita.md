# P0 — Compra importada entra com a cotação do documento aceita e o pedido registrado

**Status:** decidida — decisão do PO fechada em 11/10/2026, com uma decisão pendente do PO registrada abaixo; pendente de implementação (ver TASKS.md)
**Prioridade:** alta — única tarefa da fila

## Objetivo

Ao confirmar a revisão de um documento importado, a compra deve nascer no estado em que o negócio realmente está: **cotação do documento registrada e aceita, pedido registrado e título a pagar criado**, pronta para receber. Hoje ela nasce "em negociação", sem cotação nenhuma, e trava: não gera título no contas a pagar, não deixa enviar o pedido e não deixa receber — obrigando o comprador a cadastrar uma cotação de mentira só para destravar.

## História do usuário

Como comprador, quero confirmar o documento e já ter a compra como comprada — cotação aceita, pedido feito e título no contas a pagar —, porque o documento é a prova de que eu já comprei e estou esperando a entrega.

## Situação verificada no código (commit ffff8a2)

- `create_purchase` (`backend/app/api/routes/purchases.py`) com `source_import_id` cria a compra com `status="negotiating"`, itens já com `unit_cost`, `freight_amount`, `tax_amount` e `discount_amount` (única porta autorizada pela regra vigente de que compra digitada não tem valor) e **nenhuma** `PurchaseQuote` nem `selected_quote_id`. `_sync_payable` só é chamado nesse caminho para despesa.
- Consequências verificadas:
  - `POST /{id}/place-order` recusa: "Selecione uma cotação antes de registrar o pedido ao fornecedor".
  - `POST /{id}/receive` exige status `ordered`, `partially_received` ou `received` — a compra importada não pode ser recebida.
  - O título a pagar só nasce na seleção de uma cotação ou no recebimento; como não existe cotação, a compra importada **não aparece no contas a pagar** enquanto não for recebida.
  - O comprador fica obrigado a registrar uma cotação manual com os mesmos valores já lidos do documento para conseguir seguir.
- `add_quote` valida que a soma dos itens mais frete e impostos menos desconto fecha com o total (tolerância de R$ 0,01 por item) — a cotação criada a partir do documento precisa respeitar a mesma regra que vale para cotação registrada à mão.
- `_recompute_purchase_costs` reaplica no item o rateio da cotação: proporcional ao subtotal da linha, com a sobra de centavos no **item de maior valor** (`_split_amount`). A revisão da importação hoje joga a sobra na **última linha** (`allocateImportTotal`, `frontend/src/app/pages/purchases/purchases.ts`), então o valor revisado e o valor salvo podem divergir em centavos.
- A revisão tem "Desconto da linha" por item e um "Desconto identificado" do documento; a cotação tem um único desconto.
- `place-order` exige SKU ou produto vinculado em cada item.
- A tela do detalhe tem uma exceção para importação (`purchase.notes?.startsWith('Importação de documento.')`) no estado de "custos pendentes", que existe justamente porque a compra importada não tem cotação escolhida.

## Modelo proposto

Ao confirmar a revisão, em uma única transação, o backend:

1. Cria a compra (`purchase_type = "parts"`, `source_import_id`, fornecedor e data do documento, `needed_by` pelo prazo padrão do fornecedor quando houver) com as peças e quantidades revisadas.
2. Cria a **cotação do documento** (`PurchaseQuote`): fornecedor do documento, `item_costs` = custo unitário revisado de cada peça, `freight_amount`, `tax_amount` e `discount_amount` do documento, `allocation_method = "proportional"`, condição de pagamento padrão de compra de peças e observação `Cotação do documento importado · <nome do arquivo>`.
3. **Seleciona essa cotação** (`selected_quote_id`, status `approved`), aplica o rateio nos itens (`_recompute_purchase_costs`) e cria o **título a pagar** com a condição de pagamento.
4. Registra o **pedido** (`status = "ordered"`, `ordered_at`), porque a compra já foi feita, com evento explicando que o pedido foi registrado na importação.
5. Mantém o anexo do documento original e a revisão humana obrigatória.

Eventos do histórico, nesta ordem: `created`, `quote_received` ("Cotação do documento importado de `<fornecedor>` registrada"), `quote_selected` ("Cotação do documento aceita na importação") e `ordered` ("Pedido já realizado — registrado na importação do documento por `<usuário>`").

## Regras e decisões fechadas

1. **Documento importado é compra feita, não negociação.** A compra nasce com cotação aceita e pedido registrado, pronta para receber. Não existe etapa extra de "selecionar cotação" nem de "enviar pedido" para compra importada.
2. **O documento é a cotação da compra:** os valores lidos, revisados e confirmados por uma pessoa são gravados como a proposta do fornecedor que venceu, e passam a ser os valores dos itens, em modo leitura.
3. **O valor revisado é o valor salvo:** a revisão passa a exibir, por linha, o **custo unitário final** (base mais rateio de frete e impostos menos desconto por unidade) e, no rodapé, o fechamento `soma dos itens + frete + impostos − descontos = total do documento`. Preview e gravação usam o mesmo rateio proporcional ao subtotal da linha, com a sobra de centavos no item de maior valor.
4. **Desconto de linha não vira desconto em dobro:** o "Desconto da linha" continua visível e editável na revisão, mas é convertido no custo unitário líquido daquela linha; a cotação do documento carrega somente o desconto do documento (nível do pedido).
5. **Proposta impossível não é salva:** quando a soma dos itens não fecha com o total do documento além da tolerância de R$ 0,01 por item, quando frete mais impostos menos desconto superam o total, ou quando o desconto deixa o custo de alguma linha negativo, a confirmação é bloqueada com a diferença na mensagem e nada é criado — nem compra, nem cotação, nem título, nem pedido.
6. **SKU ou produto obrigatório por linha:** a confirmação passa a exigir, em cada item, SKU informado ou produto vinculado, com a mesma mensagem usada no envio manual do pedido, porque a compra já nasce como pedido registrado.
7. **Condição de pagamento padrão: à vista, primeiro vencimento em 30 dias corridos a partir da data do documento** (sem data do documento, a data da confirmação). O título nasce com esse vencimento e o usuário pode alterar a condição depois na compra, quando o sistema recalcula apenas as parcelas em aberto, preservando as já pagas.
8. **Idempotência preservada:** repetir a confirmação com o mesmo `source_import_id` devolve a compra já criada, sem duplicar cotação, título, pedido, eventos ou anexo.
9. **Nada muda no estoque:** a importação continua não movimentando estoque; o saldo só muda no recebimento.
10. **Compra digitada continua como está:** sem documento, a compra de peças segue nascendo sem valor e sem cotação, e o preço entra somente pela cotação do fornecedor.
11. **A compra importada passa a se comportar como qualquer compra aprovada:** cotação vencedora travada para edição, valores por item somente leitura, título no contas a pagar e recebimento parcial ou total.
12. **Limpeza:** a exceção de "custos pendentes" para importação no detalhe da compra deixa de existir, porque agora há cotação escolhida de verdade.
13. *Decisão pendente do PO: extrair do documento (ou digitar na revisão) a **condição de pagamento** e a **previsão de entrega**. Enquanto a decisão não for tomada, a revisão não pede esses campos e vale a condição padrão da regra 7; o prazo de entrega do fornecedor cadastrado continua preenchendo `needed_by`.*

## Casos de borda

- Documento sem total lido: o total é calculado pela soma dos itens mais frete e impostos menos descontos, e é esse valor que a revisão mostra antes de confirmar.
- Total do documento diferente da soma: confirmação bloqueada com a diferença e a indicação de conferir linhas, frete, impostos e desconto.
- Frete mais impostos menos desconto maior que o total: bloqueado com o motivo (proposta impossível).
- Linha sem SKU e sem produto vinculado: bloqueado com a mensagem do pedido do fornecedor.
- Fornecedor não cadastrado: a cotação usa o nome lido do documento; o cadastro leve de fornecedor continua disponível no fluxo.
- Reenvio, duplo clique ou repetição depois de falha de rede: uma única compra, uma única cotação, um único título, um único pedido.
- Anexo falhou depois da compra criada: a compra permanece válida e o aviso atual continua valendo; o documento pode ser anexado depois.
- Documento importado que era só uma proposta (orçamento): o caminho de correção é cancelar a compra, que encerra o título com estorno; um fluxo paralelo de "importar proposta" não é criado nesta fase.
- Importação de documento de despesa: fora do escopo; a importação continua sendo de peças.

## Fora de escopo

- Extrair ou digitar condição de pagamento e previsão de entrega na revisão (decisão pendente do PO, regra 13).
- Alterar perfis de reconhecimento, OCR e leiaute por plataforma, e o vínculo de itens a produtos do estoque.
- Criar ou alterar o motor de rateio da cotação, o cálculo bidirecional de total e preço unitário e a geração das parcelas do título.
- Deixar a compra digitada com valor: a compra manual continua sem campo monetário.
- Criar produto automaticamente ou vincular produto por semelhança textual.
- Importar documento de venda, de despesa ou de nota de saída.

## Critérios de aceite

1. Confirmar a importação de um documento de peças cria a compra com uma cotação registrada, já selecionada, status "pedido registrado" e `ordered_at` preenchido.
2. O título a pagar passa a existir imediatamente, com o valor da cotação e vencimento na data do documento mais 30 dias corridos (condição padrão), aparecendo no contas a pagar.
3. O detalhe da compra mostra a cotação escolhida travada e, por peça, o custo unitário final igual ao valor exibido na revisão, centavo a centavo.
4. O recebimento total e parcial fica disponível logo após confirmar, sem passar por "selecionar cotação" nem "enviar pedido".
5. Quando a soma dos itens mais frete e impostos menos descontos não fecha com o total do documento, a confirmação é bloqueada com a diferença na mensagem e nada é criado.
6. Linha sem SKU e sem produto vinculado bloqueia a confirmação com a mensagem do pedido do fornecedor.
7. Repetir a confirmação com o mesmo identificador de importação devolve a mesma compra, sem duplicar cotação, título, pedido, eventos nem anexo.
8. A revisão mostra o custo unitário final por linha e o fechamento do total antes de confirmar, e o total revisado é igual ao total da cotação e ao valor do título.
9. Frete mais impostos menos desconto acima do total, ou desconto que deixe o custo de uma linha negativo, bloqueia a confirmação com o motivo.
10. O histórico da compra registra criação, cotação do documento, aceite da cotação e registro do pedido, com autor e horário; datas persistidas em UTC e exibidas em `America/Sao_Paulo` (`pt-BR`).
11. Nenhum movimento de estoque é criado na importação; o saldo só muda no recebimento.
12. Compra digitada sem documento continua nascendo sem valor, sem cotação e sem título.
13. O detalhe da compra importada não usa mais a exceção de "custos pendentes" por observação de importação.
14. O recebimento de uma compra importada atualiza custo médio e estoque usando os valores da cotação do documento, como em qualquer compra com cotação escolhida.

## Verificação

- Testes de backend em `backend/tests/test_purchase_import.py`: criação com cotação aceita e pedido registrado, título com a condição padrão, fechamento do total com bloqueio, SKU obrigatório, idempotência por `source_import_id` e ausência de movimento de estoque.
- Teste de rateio comparando o preview da revisão com os valores persistidos nas mesmas entradas, inclusive casos com sobra de centavos e várias linhas.
- HML local: importar um documento de amostra (recibo de plataforma e NF-e já suportados), conferir a revisão com custo final por linha, confirmar, verificar detalhe da compra, título no contas a pagar, recebimento parcial e a lista de compras.
- Conferir a tela em desktop e em viewport móvel estreito, incluindo as mensagens de bloqueio.
