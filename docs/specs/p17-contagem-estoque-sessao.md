# P17 — Contagem de estoque com ajuste auditado

**Status:** decidida — decisões do PO fechadas em 11/10/2026; pendente de implementação (ver TASKS.md)
**Prioridade:** P6 da fila — baixa

## Objetivo

Organizar a conferência física do estoque em **sessões de contagem**: preparar a lista de peças por escopo, contar com o esperado congelado, comparar e lançar um único ajuste auditado por item divergente. Hoje só existe ajuste produto a produto com motivo livre, sem registro da conferência, o que torna a contagem de uma prateleira inteira lenta e impossível de auditar depois.

## História do usuário

Como responsável pelo estoque, quero abrir uma contagem, percorrer a prateleira informando o que encontrei e fechar a sessão de uma vez, para corrigir o saldo com motivo registrado em vez de lançar dezenas de ajustes soltos sem rastro.

## Situação verificada no código (commit ffff8a2)

- `POST /api/products/{product_id}/adjust-stock` aceita um ajuste por produto, com motivo em texto livre, exige a permissão `inventory:adjust` e publica o saldo nos canais.
- A edição da ficha da peça também gera ajuste com motivo fixo "Ajuste de saldo pela edição da peça" (`frontend/src/app/pages/products/products.ts`).
- Não existe modelo de sessão, lista preparada, quantidade esperada congelada, relatório de divergência nem exportação.
- A página Produtos tem o painel "Ajustar estoque" (quantidade + motivo) e o dashboard aponta para ele.
- `move_stock` valoriza o movimento pelo custo atual do produto e **não** altera o custo médio em movimentos de ajuste.

## Escopo

- Nova área **Contagem de estoque**, no menu Análise, ao lado de Contas a pagar, com a lista de sessões (abertas, fechadas e descartadas), responsável, data e resumo de divergências.
- Criação de sessão com nome automático (por exemplo `Contagem 11/10/2026`), data da contagem (padrão hoje, `America/Sao_Paulo`) e escopo: todas as peças ativas, por categoria, por marca, somente abaixo do mínimo, ou lista de SKUs informada/escaneada.
- Ao criar, o sistema congela a quantidade esperada e o custo unitário de referência de cada item do escopo.
- Tela de contagem: por item, SKU, nome, esperado, campo de quantidade contada (aceita 0), observação e marcação visual de divergência; leitura/busca por SKU para quem usa leitor de código de barras.
- Fechamento da sessão lançando um ajuste por item divergente e gerando relatório; exportação em CSV com o mesmo padrão do contas a pagar (separador `;` e BOM, abre no Excel pt-BR).

## Regras e decisões fechadas

1. **O esperado é congelado na criação da sessão.** Movimentos posteriores não alteram o esperado; o relatório mostra o esperado congelado, o saldo no momento do fechamento e o sinal "movimentado durante a contagem" quando os dois diferirem.
2. **Diferença lançada = contado − saldo no fechamento.** No fechamento, o saldo do item passa a ser exatamente o valor contado, com um movimento `adjustment` por item divergente, motivo `Contagem {número} · divergência {+/-N}` e referência `count:{id da sessão}`.
3. **Item sem divergência não gera movimento.** Contar o valor que já está no sistema não cria histórico de ajuste, apenas o registro da conferência.
4. **Em branco não é zero.** Campo vazio significa "não contado"; digitar `0` significa "contei e não há nenhum". Só o segundo caso entra na comparação.
5. **Fechar com pendências é permitido com confirmação:** itens não contados aparecem no relatório como "não contado" e não geram ajuste.
6. **Observação obrigatória em divergência relevante:** o fechamento fica bloqueado enquanto um item com divergência de 5 unidades ou mais, ou de 10% ou mais do esperado, estiver sem observação.
7. **Sessão fechada ou descartada é imutável.** Correção depois do fechamento é uma nova contagem, que traz o histórico anterior como referência.
8. **O ajuste nunca deixa saldo negativo**, porque o saldo passa a ser o valor contado, sempre maior ou igual a zero; a regra atual de estoque é preservada.
9. **O custo médio do produto não é alterado** pela contagem; o movimento é valorizado pelo custo de referência congelado e o relatório mostra o valor da divergência.
10. **Leitura repetida do mesmo SKU substitui o valor anterior**, com aviso na tela; a contagem não soma leituras.
11. **Escopo por categoria ou marca considera apenas peças ativas.** Peça inativa só entra quando citada explicitamente na lista de SKUs, com aviso na tela.
12. **Sessões abertas simultâneas são permitidas**, com aviso quando já existe sessão aberta sobrepondo o escopo escolhido.
13. **Ajuste avulso continua existindo** e passa a registrar a origem (manual ou contagem), mantendo o painel atual da página Produtos.
14. **Permissões:** criar, contar, fechar e descartar exigem `inventory:adjust` (admin/manager); leitura das sessões segue `products:read`.
15. **Publicação nos canais:** o fechamento usa a publicação unificada de estoque (P13), de modo que o anúncio acompanhe o saldo corrigido.
16. **Datas:** o instante de criação, fechamento e dos movimentos é persistido em UTC e exibido em `America/Sao_Paulo` (`pt-BR`); a data da contagem é data de calendário, sem deslocamento de fuso.

## Casos de borda

- Sessão criada e nunca usada: pode ser descartada, com registro de quem descartou e quando; nenhum ajuste é lançado.
- Escopo sem nenhuma peça (categoria vazia): a criação é recusada com mensagem explicando que não há itens para contar.
- Lista de SKUs com duplicidade: cada SKU aparece uma vez; SKU inexistente é listado como aviso e não cria item.
- Peça vendida durante a contagem: o relatório mostra "movimentado durante a contagem" e o saldo final passa a ser o contado (regra 2).
- Peça zerada no sistema e encontrada com 3 unidades: ajuste de +3, com observação se a divergência atingir o limite da regra 6.
- Peça com 12 unidades no sistema e nenhuma na prateleira: contado 0, ajuste de −12, exigindo observação pela regra 6.
- Quantidade fracionada conforme a unidade da peça: aceita até 3 casas.
- Duas sessões fechadas no mesmo dia: relatórios independentes e identificados pelo número.

## Fora de escopo

- Contagem cíclica automática, agendada ou por curva ABC.
- Endereço físico, prateleira, bin ou múltiplos almoxarifados.
- Inventário contábil, avaliação de estoque, laudo de perda e baixa fiscal.
- Bloqueio de venda ou de ajuste durante a contagem e reserva de estoque.
- Leitor de código de barras dedicado, aplicativo de contagem offline e integração com coletor.

## Critérios de aceite

1. É possível criar uma sessão escolhendo escopo por categoria, marca, abaixo do mínimo, todas as peças ativas ou lista de SKUs, e a lista de itens é gerada com o esperado congelado.
2. Informar quantidade contada em parte dos itens e fechar a sessão lança exatamente um movimento de ajuste por item divergente, com motivo contendo o número da sessão e o valor da divergência.
3. Itens contados sem divergência não geram movimento, e itens não contados não são ajustados.
4. Peça com esperado 12 e contado 0 gera ajuste de −12; peça com esperado 0 e contado 3 gera ajuste de +3.
5. O fechamento fica bloqueado enquanto um item com divergência de 5 unidades ou mais, ou 10% ou mais do esperado, estiver sem observação preenchida.
6. Vender uma peça durante a sessão marca o item como "movimentado durante a contagem" no relatório, e o saldo final passa a ser o valor contado.
7. O relatório mostra esperado, saldo no fechamento, contado, divergência, valor da divergência, observação e situação de cada item, com exportação CSV legível no Excel pt-BR.
8. A peça ajustada pela contagem tem o saldo publicado nos anúncios vinculados e o custo médio do produto permanece inalterado.
9. Sessão fechada não aceita mais contagem nem reabertura; uma nova sessão preserva o histórico da anterior.
10. Usuário sem `inventory:adjust` vê a lista e o relatório das sessões, sem as ações de criar, contar, fechar ou descartar.
11. Datas de criação, fechamento e movimentos aparecem em `America/Sao_Paulo` sem deslocamento de um dia, em desktop e mobile.

## Verificação

- Testes de backend (`backend/tests/test_stock_count.py`): congelamento do esperado, diferença lançada no fechamento, item não contado, observação obrigatória, imutabilidade da sessão fechada, publicação nos canais e valorização do movimento.
- HML local: criar uma sessão por categoria com peças divergentes e não contadas, fechar, conferir o relatório, o CSV, o histórico das peças e o saldo publicado nos canais.
- Conferir a tela de contagem em desktop e em viewport móvel estreito, incluindo o campo de busca por SKU.
