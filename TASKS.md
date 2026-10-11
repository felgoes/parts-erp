# Lista de tarefas — Parts ERP

## Pendentes

- [ ] [P13] Estoque publicado coerente em cada canal.
  Receber compra, devolver ao fornecedor, ajustar o saldo e vender já movimentam estoque, mas só parte desses eventos publica a nova quantidade nos anúncios do Mercado Livre e da Shopee: o recebimento de compra e o retorno de devolução ao estoque não publicam e a falha de canal é descartada em silêncio. O anúncio fica com menos peças do que existem, a venda se perde e não há como saber qual anúncio está desatualizado. A entrega publica em todo ponto que altera saldo, registra pendência e erro por anúncio, retenta pelo worker e mostra a lista de divergências com "Publicar agora".
  Spec: docs/specs/p13-estoque-publicado-canais.md

- [ ] [P14] Reposição sugerida que gera o rascunho da compra.
  O ERP conhece o estoque mínimo, o saldo atual, o que já está em pedido e o giro de venda do período, mas não diz o que comprar: hoje a decisão sai da leitura de tela em tela. A entrega acrescenta a área "Reposição" com o filtro de período compartilhado, calcula a quantidade sugerida por produto (mínimo + consumo previsto − saldo − em pedido), mostra custo estimado e fornecedor habitual e converte a seleção em rascunhos de compra por fornecedor, só com peças e quantidades, sem valores, conforme a P9.
  Spec: docs/specs/p14-reposicao-sugerida-compra.md

- [ ] [P15] Devolução pontual ao fornecedor com crédito no título a pagar.
  A devolução de peças recebidas só existe hoje dentro do cancelamento da compra inteira, que encerra o título a pagar e joga fora o registro dos itens bons; não há caminho para devolver uma peça com defeito mantendo o resto do pedido. A entrega cria a ação "Devolver ao fornecedor" no detalhe da compra, com motivo estruturado, baixa de estoque documentada e crédito de valor que reduz o que ainda está em aberto no título, mantendo as parcelas já pagas.
  Spec: docs/specs/p15-devolucao-fornecedor-credito-titulo.md

- [ ] [P16] Catálogo público com disponibilidade e preço do anúncio.
  A consulta pública do catálogo devolve o preço de venda interno do cadastro e marca "tem estoque" pelo saldo do ERP, sem olhar a situação do anúncio, e ainda entrega permalink de anúncio pausado ou encerrado, que vira link morto para o visitante. A entrega passa a responder disponibilidade (disponível, esgotado, sob consulta) e preço a partir dos anúncios ativos, com menor preço entre anúncios ativos, link só quando o anúncio está ativo, busca e paginação no servidor.
  Spec: docs/specs/p16-catalogo-publico-disponibilidade-preco.md

- [ ] [P17] Contagem de estoque com ajuste auditado.
  O ajuste de saldo existe somente produto a produto, com motivo livre e sem registro da conferência física: não há lista preparada, quantidade esperada congelada nem relatório de divergência, o que torna a conferência de uma prateleira inteira lenta e impossível de auditar. A entrega cria sessões de contagem por escopo (categoria, marca, abaixo do mínimo ou lista de SKUs), congela o esperado na abertura, lança um ajuste por item divergente com autor e motivo da sessão e exporta o relatório em CSV.
  Spec: docs/specs/p17-contagem-estoque-sessao.md

## Concluídas

## Encerradas sem implementação

## Fila solicitada

---

Fila priorizada em 11 de outubro de 2026 (ordem de execução): **P13 → P14 → P15 → P16 → P17**.
Primeira tarefa da fila: **P13 — Estoque publicado coerente em cada canal** (prioridade alta).
Prioridades: P13 e P14 altas; P15 e P16 médias; P17 baixa. Itens anteriores, concluídos ou encerrados, permanecem no histórico do Git e no `RELEASE_NOTES.md`.
