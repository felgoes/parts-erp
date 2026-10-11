# P16 — Catálogo público com disponibilidade e preço do anúncio

**Status:** decidida — decisões do PO fechadas em 11/10/2026, com uma decisão pendente do PO registrada abaixo; pendente de implementação (ver TASKS.md)
**Prioridade:** P4 da fila — média

## Objetivo

Fazer o catálogo público mostrar o que o cliente realmente pode comprar: disponibilidade derivada dos anúncios ativos e preço igual ao praticado no anúncio, sem expor preço interno divergente e sem publicar link morto de anúncio pausado ou encerrado. O catálogo é a vitrine da loja; hoje ele responde com dado que pode estar errado e leva o visitante a um anúncio que não existe mais.

## História do usuário

Como visitante do site, quero ver se a peça está disponível e por quanto ela está à venda de verdade, para não perder tempo pedindo peça que não tem nem estranhando um preço diferente do anúncio. Como lojista, quero que a vitrine acompanhe o que publiquei, sem mostrar preço interno nem link quebrado.

## Situação verificada no código (commit ffff8a2)

- `backend/app/api/routes/catalog.py` (`GET /api/catalog/products`) devolve `sale_price` (preço de venda do cadastro interno), `in_stock = current_stock > 0` e todos os anúncios com `external_item_id`, **sem olhar `status`** nem a `available_quantity` publicada.
- A busca e o recorte são feitos em memória: todos os produtos ativos são carregados e filtrados em Python, com `limit` de 48 por padrão (máximo 100) e sem total de resultados.
- `_listing_permalink` fabrica um permalink do Mercado Livre a partir do identificador quando o anúncio não tem permalink salvo — inclusive para anúncio pausado ou encerrado.
- `ProductMarketplaceListing` já guarda `status`, `available_quantity`, `marketplace_price` e `synchronized_at`.
- A página pública do catálogo (`frontend/src/app/pages/catalog/catalog.ts`) é servida pelo projeto do site em www; o comentário em `frontend/src/app/app.routes.ts` registra que o catálogo público é hospedado fora do host do ERP.

## Escopo

- Revisar o contrato de `GET /api/catalog/products` para responder disponibilidade e preço a partir dos anúncios ativos, com busca e paginação no servidor (`page`, `page_size`, total de resultados) e ordenação estável.
- Novo campo por produto: `availability` com os valores `in_stock`, `out_of_stock` e `on_request`; novo campo `price_from` (verdadeiro quando há mais de um preço ativo); `updated_at` com o instante UTC da sincronização mais recente dos anúncios exibidos.
- Por anúncio: situação, preço, quantidade publicada e permalink **somente** quando o anúncio estiver ativo.
- Ajustar a página do catálogo deste repositório para exibir "Disponível", "Sem estoque", "Sob consulta", "a partir de R$ X" e o aviso de atualização, preservando o layout atual.

## Regras e decisões fechadas

1. **Anúncio ativo** é o anúncio publicado e disponível no canal (`status = active`, sem diferenciar maiúsculas). Pausado, encerrado, em revisão ou em erro não é ativo para o catálogo.
2. **Disponibilidade:** `in_stock` quando existe anúncio ativo com quantidade publicada maior que zero; `out_of_stock` quando existe anúncio ativo com quantidade zero; `on_request` quando não existe anúncio ativo.
3. **Preço exibido** é o preço do anúncio ativo. Com mais de um anúncio ativo em canais ou anúncios diferentes, o valor mostrado é o **menor preço ativo** e `price_from` fica verdadeiro ("a partir de"). Sem anúncio ativo com preço, não há preço exibido.
4. **O preço interno do cadastro (`sale_price`/`cost_price`) deixa de ser publicado.** Compatibilidade: a chave `sale_price` continua existindo na resposta por uma versão, mas passa a carregar o preço público da decisão 3 e volta nula quando não existe preço de anúncio ativo. `cost_price` nunca aparece na resposta pública.
5. **Sem link morto:** o permalink só é devolvido para anúncio ativo; sem anúncio ativo, a resposta não traz permalink e o cartão do catálogo leva ao contato da loja.
6. **Disponibilidade não é saldo interno isolado:** peça com saldo alto e anúncio pausado aparece como "sob consulta", não como "disponível".
7. **Busca e paginação no banco:** a consulta filtra em SQL (nome, SKU, descrição, título do anúncio, número de peça do fabricante, código de barras e atributos relevantes) e devolve total de resultados; a listagem não carrega a base inteira na memória. `page_size` padrão 24, máximo 100.
8. **Ordenação:** correspondência exata de SKU ou número de peça primeiro, depois peças disponíveis e depois as demais, sempre com nome como critério de desempate.
9. **Produtos sem anúncio ativo continuam visíveis** como "sob consulta" — *decisão pendente do PO: manter as peças sem anúncio ativo visíveis no catálogo público ou ocultá-las até serem publicadas; a implementação mantém visíveis enquanto a decisão não for tomada.*
10. **Peça inativa (`active = false`) nunca aparece** no catálogo público.
11. **Quantidade publicada exibida é inteira** (`floor`) e nunca negativa, coerente com a P13.
12. **Dependência externa:** o site público em www consome este contrato e precisa passar a usar `availability`, `price_from` e `permalink` opcional na mesma janela de entrega; este repositório entrega o contrato e a página do catálogo, e a coordenação com o projeto do site é parte da verificação.

## Casos de borda

- Peça ativa com anúncio pausado temporariamente e saldo em estoque: `on_request`, sem preço e sem link.
- Peça com dois anúncios ativos e preços diferentes: menor preço com "a partir de" e preço do outro anúncio visível no detalhe da peça.
- Peça com anúncio ativo e quantidade publicada zero: `out_of_stock`, mantendo o permalink do anúncio ativo.
- Anúncio ativo sem preço informado no canal: sem preço exibido, mantendo a disponibilidade.
- Busca por SKU com hífen, ponto ou acento: encontra pelo valor normalizado.
- Busca sem resultado: resposta vazia com total zero, sem erro.
- Página além do total disponível: resposta vazia, sem erro e sem repetir itens da página anterior.
- Peça sem imagem: mantém o comportamento atual de placeholder.
- Base grande: a primeira página responde sem carregar todos os produtos ativos.

## Fora de escopo

- Redesenhar a identidade visual, o layout ou o conteúdo editorial do site público.
- SEO, dados estruturados, sitemap e indexação.
- Carrinho, checkout, pedido ou pagamento pelo site.
- Publicar estoque no marketplace (é a P13) e criar anúncio novo.
- Regras de preço promocional, cupom ou preço por canal.

## Critérios de aceite

1. Peça com anúncio ativo e quantidade publicada 4 responde `in_stock` e o preço do anúncio ativo.
2. Peça com anúncio ativo e quantidade zero responde `out_of_stock`, com o mesmo preço e permalink do anúncio ativo.
3. Peça sem anúncio ativo responde `on_request`, sem preço e sem permalink.
4. Peça com saldo interno positivo e anúncio pausado responde `on_request`, e o catálogo não mostra "disponível" nem o preço interno do cadastro.
5. Peça com dois anúncios ativos de preços diferentes devolve o menor preço com `price_from` verdadeiro.
6. A resposta pública não contém `cost_price` em nenhuma hipótese.
7. A busca filtra por nome, SKU, número de peça do fabricante, código de barras e título do anúncio, com paginação e total de resultados corretos em uma página e na seguinte.
8. A ordenação coloca a correspondência exata de SKU ou número de peça antes das demais.
9. A página do catálogo mostra "Disponível", "Sem estoque" e "Sob consulta" conforme a resposta, com "a partir de" quando aplicável, em desktop e em viewport móvel estreito.
10. O aviso de atualização do catálogo usa o `updated_at` mais recente dos anúncios exibidos, exibido em `America/Sao_Paulo` (`pt-BR`) e persistido em UTC.
11. O consumo pelo site público funciona com o contrato novo, e a chave `sale_price` mantida por compatibilidade não expõe o preço interno.

## Verificação

- Estender `backend/tests/test_catalog.py` com disponibilidade por situação de anúncio, preço mínimo entre anúncios ativos, ausência de preço interno, permalink só para anúncio ativo, paginação e total, e ordenação por correspondência exata.
- Consultar a API em HML local com peças em cada situação (anúncio ativo com e sem estoque, pausado, sem anúncio) e conferir a página do catálogo em desktop e mobile.
- Conferir com o projeto do site que os campos novos são consumidos e que nenhum cartão aponta para anúncio encerrado.
