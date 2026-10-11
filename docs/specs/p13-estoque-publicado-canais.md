# P13 — Estoque publicado coerente em cada canal

**Status:** decidida — decisões do PO fechadas em 11/10/2026; pendente de implementação (ver TASKS.md)
**Prioridade:** P2 da fila — alta

## Objetivo

Fazer a quantidade publicada em cada anúncio do Mercado Livre e da Shopee acompanhar o saldo real do ERP em **toda** movimentação de estoque, com falha de canal registrada, retentativa automática e uma visão objetiva do que está desatualizado. Hoje parte dos eventos publica e parte não, e a falha é descartada em silêncio: o anúncio mostra menos peças do que a loja tem, a venda se perde e ninguém sabe qual anúncio está fora de linha.

## História do usuário

Como responsável pela loja, quero que o anúncio mostre sempre a quantidade que eu realmente tenho — inclusive depois de receber uma compra ou de uma devolução de cliente voltar ao estoque — para não perder venda nem anunciar peça que não existe.

## Situação verificada no código (commit ffff8a2)

- `backend/app/services/product_channels.py` (`sync_product_stock_all`) publica a quantidade nos canais conectados.
- Ele é chamado apenas por: ajuste de estoque do produto, botão manual "Sincronizar estoque nos anúncios" e confirmação/cancelamento de fatura de venda (`backend/app/api/routes/invoices.py`).
- O recebimento de compra (`backend/app/api/routes/purchases.py`, `_apply_receipt`) altera o saldo com `move_stock` e **não publica** em nenhum canal.
- O retorno de devolução de cliente ao estoque (`backend/app/services/after_sale.py`) altera o saldo e **não publica** em nenhum canal.
- A falha de canal é engolida com `db.rollback()`. O comentário do código ("a sincronização será tentada no próximo ciclo") não tem ciclo correspondente: o worker `arq` (`backend/app/workers/settings.py`) não tem job de estoque.
- O anúncio já guarda `sync_status`, `sync_error`, `synchronized_at` e `available_quantity`, mas nada consome esses campos para sinalizar pendência.

## Escopo

- Centralizar a publicação em um único caminho (`publicar_estoque(produto)`), chamado por **todo** ponto que altera saldo: recebimento de compra (total ou parcial), ajuste de estoque (avulso e pela edição da ficha), confirmação de venda, cancelamento de venda, retorno de devolução de cliente ao estoque, devolução ao fornecedor (P15) e vínculo/republicação de anúncio.
- Registrar por anúncio: quantidade publicada, situação da última publicação (`sincronizado`, `pendente`, `erro`), instante UTC da última publicação bem-sucedida, mensagem de erro da última tentativa e número de tentativas.
- Fila de pendências no worker `arq`, no mesmo padrão já usado por `reconcile_pending_marketplace_documents` e `retry_due_mercadolivre_orders`: job de minuto em minuto publicando o que está pendente; após 5 tentativas o anúncio fica em `erro` e para de repetir sozinho, aguardando ação manual.
- Tela: na página Produtos, uma visão "Estoque publicado" (aba ou seção, com o mesmo padrão visual das demais listas) mostrando os anúncios com divergência entre o saldo do ERP e a quantidade publicada, com filtro por canal e por situação, ação "Publicar agora" por linha e "Publicar tudo" para os pendentes.
- Visibilidade do estado no detalhe da peça: cada anúncio vinculado mostra situação, quantidade publicada e, em erro, a mensagem do canal.

## Decisões fechadas

1. **A operação local nunca falha por causa do canal.** Salvar compra, receber, ajustar saldo, vender, cancelar e devolver seguem valendo mesmo com o marketplace fora do ar; a publicação vira pendência.
2. **Falha deixa de ser silenciosa.** Cada tentativa malsucedida grava situação, mensagem e horário no anúncio; nada é descartado sem registro.
3. **A quantidade publicada é `floor(saldo)`.** Peças fracionadas nunca são publicadas para cima (2,7 publica 2) e o valor nunca é negativo (saldo negativo ou zero publica 0).
4. **Anúncio pausado, encerrado ou em rascunho não recebe publicação** e aparece na visão como "pausado", não como pendência de estoque.
5. **A quantidade publicada é sempre o saldo atual no momento da execução**, não o saldo do instante do evento; movimentos ocorridos durante uma retentativa não geram publicação duplicada nem atrasada.
6. **Publicação é idempotente:** repetir publica a mesma quantidade, sem criar movimento de estoque nem histórico paralelo.
7. **Preço, título, imagens e atributos ficam fora**: esta tarefa publica apenas quantidade.
8. **Estoque publicado é a fonte do catálogo público** (P16): a quantidade mostrada ao visitante é a que foi publicada no anúncio.
9. **Erro de credencial é tratado como erro de canal**, com mensagem orientando reconectar a conta em Integrações; não gera retentativa infinita.

## Casos de borda

- Canal sem conta conectada ou conta desativada: produto não entra em pendência.
- Peça sem anúncio vinculado (`external_item_id` vazio) não é pendência.
- Peça com mais de um anúncio: publicar em todos; falha em um não cancela os outros.
- Saldo fracionado e saldo zero: aplicar a decisão 3, sem pausar nem republicar o anúncio automaticamente.
- Movimentação durante a retentativa: publicar o saldo atual (decisão 5).
- Anúncio pausado pelo vendedor com saldo alterado: não publicar e sinalizar "pausado — publicação pendente para quando reativar".
- Saldo alterado repetidamente em pouco tempo: uma publicação por produto por execução do job, sem fila duplicada.
- Duplo clique em "Publicar agora": uma publicação efetiva, sem duplicar histórico.

## Fora de escopo

- Publicar preço, título, descrição, imagens ou atributos; criar anúncio novo.
- Pausar, reativar ou encerrar anúncio automaticamente por falta de estoque (exigiria decisão comercial própria; registrar como decisão pendente do PO se o dono do produto pedir).
- Importar a quantidade do anúncio para o ERP: o ERP é a fonte da verdade do saldo.
- Publicar estoque de materiais de almoxarifado, que não têm anúncio.
- Recalcular preço, margem ou comissão do canal.

## Critérios de aceite

1. Receber uma compra de peças com anúncio vinculado publica a nova quantidade nos dois canais e a visão mostra "sincronizado" com data e hora.
2. Recebimento parcial publica a quantidade intermediária, e não a quantidade pedida.
3. Devolução de cliente aprovada com retorno ao estoque publica o saldo resultante.
4. Venda confirmada e cancelamento de venda continuam publicando como hoje, sem regressão.
5. Com o canal indisponível, o recebimento é concluído com sucesso, o anúncio fica "pendente" com a mensagem do erro e a execução seguinte do job publica sem ação do usuário.
6. Após 5 tentativas malsucedidas o anúncio fica em "erro" e não repete sozinho; "Publicar agora" refaz a publicação e devolve a situação para "sincronizado".
7. A visão "Estoque publicado" lista somente anúncios com divergência entre saldo e quantidade publicada, com filtro por canal e situação, e não lista anúncios pausados como pendência.
8. Peça com saldo 2,7 publica 2; peça com saldo 0 publica 0; nunca é publicado valor negativo.
9. Devolução ao fornecedor (P15) e ajuste de estoque pela edição da ficha também publicam o saldo.
10. Nenhuma falha de canal impede salvar compra, receber, ajustar saldo, confirmar venda, cancelar venda ou registrar devolução; e reenvio não duplica publicação.
11. Horários de tentativa e de última publicação são persistidos em UTC e exibidos em `America/Sao_Paulo` com locale `pt-BR`.

## Verificação

- Novo teste de backend (`backend/tests/test_stock_publication.py`) cobrindo: recebimento total, recebimento parcial, retorno de devolução, venda, cancelamento, falha de canal, retentativa e limite de tentativas.
- HML local: receber uma compra de peça com anúncio vinculado e conferir a quantidade publicada, a lista de divergências e o estado em erro simulado (canal indisponível).
- Conferir a visão em desktop e em viewport móvel estreito, com valores de saldo fracionado.
