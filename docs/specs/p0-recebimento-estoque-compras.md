# P0 — Receber itens de compras no almoxarifado

**Status:** concluída — implementada e implantada em PRD em 09/10/2026 (commit `747227f`, nota "Recebimento de materiais de despesas"), com site e ERP em HTTP 200; critérios de aceite e decisões conferidos no código em 11/10/2026
**Prioridade:** P0

## Objetivo

Registrar despesas da empresa e, quando a compra incluir materiais físicos controlados, receber suas quantidades no almoxarifado. O lançamento financeiro e o controle físico são dados relacionados, mas independentes: uma despesa pode ter itens de estoque ou não.

## Modelo proposto

- O tipo financeiro permanece **Despesa da empresa**.
- A despesa recebe uma categoria financeira. Para fita crepe, caixas e outros consumíveis, usar a categoria **Materiais de consumo e embalagem**, a ser adicionada às opções atuais.
- A despesa pode ter linhas de itens controlados no estoque. Cada linha informa produto, descrição, unidade, quantidade e custo.
- Uma despesa sem itens continua funcionando para aluguel, internet, serviços e outros gastos sem saldo físico.
- Compra de peças para revenda mantém o fluxo atual **Peças para estoque**.
- O valor da despesa é lançado uma vez e vinculado às linhas recebidas. Receber em partes atualiza quantidades, sem criar novos lançamentos financeiros.

## História do usuário

Como responsável pela empresa e pelo estoque, quero registrar uma compra como despesa na categoria correta e controlar no almoxarifado os materiais físicos que ela contém, para acompanhar tanto o gasto quanto o saldo disponível.

## Escopo

- Na compra do tipo **Despesa da empresa**, permitir adicionar opcionalmente linhas de materiais controlados no estoque.
- Para cada linha, informar/selecionar produto, unidade, quantidade, custo unitário e quantidade recebida.
- A partir do detalhe da compra, receber total ou parcialmente itens ainda pendentes.
- Mostrar quantidade comprada, recebida anteriormente, pendente e quantidade deste recebimento.
- O destino é o almoxarifado único da empresa; creditar diretamente o saldo de estoque do produto, sem seleção de local.
- Ao confirmar, registrar entrada de estoque e histórico vinculado à compra, item, usuário e data/hora.
- Criar/manter somente um lançamento financeiro do tipo **Despesa da empresa**, na categoria selecionada e pelo valor da despesa.
- Se o produto não existir, permitir criá-lo explicitamente com os campos obrigatórios do cadastro padrão e vinculá-lo à linha.
- Manter o recebimento de **Peças para estoque** existente.

## Regras de negócio

- Uma despesa pode existir sem itens de estoque. Itens físicos não podem ser lançados somente como uma descrição livre se o usuário deseja controlar saldo.
- Quantidades devem ser positivas e compatíveis com a unidade cadastrada. O total recebido não pode exceder o comprado sem regra de autorização explícita.
- Recebimentos parciais não duplicam o lançamento financeiro nem a movimentação de estoque em caso de reenvio.
- A criação do produto deve ser explícita. Verificar correspondências para evitar duplicidade; não inventar SKU ou outros dados ausentes.
- Confirmar recebimento é a única ação que aumenta o saldo. Criar a despesa ou o pedido não aumenta o estoque.
- Se houver divergência, avaria ou substituição, registrar observação sem alterar silenciosamente os dados da compra.
- Registrar a despesa uma única vez no fluxo financeiro existente. A data de pagamento/competência deve seguir o comportamento atual do ERP; recebimento físico não pode gerar outro débito.

## Fora de escopo

- Contabilidade por competência, baixa automática do custo do consumível no momento de uso, centro de custos ou rateio de uma fatura entre várias categorias.
- Entrada avulsa sem compra, transferência entre almoxarifados, inventário/ajuste e devolução ao fornecedor.
- Conversão automática entre unidades incompatíveis.
- Controle de lote, validade ou número de série.

## Critérios de aceite

1. É possível salvar uma despesa sem itens de estoque, por exemplo aluguel.
2. É possível registrar fita crepe ou caixas como despesa na categoria de materiais de consumo e embalagem e incluir linhas controladas no estoque.
3. O usuário consegue receber todos ou parte dos itens e consultar quantidades compradas, recebidas e pendentes.
4. O recebimento credita apenas a quantidade confirmada ao saldo de estoque do produto.
5. O valor/categoria da despesa aparece uma vez; recebimentos parciais não criam despesas duplicadas.
6. Quantidades inválidas ou acima do permitido impedem confirmação e explicam o motivo.
7. Reenvio/duplo clique não duplica movimentos de estoque ou financeiros.
8. Cada movimento permite rastrear compra, item, quantidade, autor e horário.
9. Produto ausente pode ser criado explicitamente pelo cadastro padrão e vinculado; não ocorre criação silenciosa nem duplicação.
10. O fluxo atual de compra de peças para revenda continua recebendo itens no estoque.

## Decisões resolvidas na implementação

- **Lançamento financeiro único:** a despesa gera um único título a pagar vinculado à compra, reconstruído por `_sync_payable` a partir do valor devido; recebimentos parciais não criam outro lançamento.
- **Almoxarifado único:** materiais controlados usam `stock_type = warehouse`, sem seleção de local e sem múltiplos almoxarifados.
- **Cadastro rápido de produto:** exige SKU e nome; os demais campos do cadastro padrão são opcionais e nenhum dado é inventado. O cadastro só acontece por ação explícita (cadastro no vínculo do item ou "Criar produto no catálogo ao receber").
- **Recebimento acima do comprado:** bloqueado com HTTP 409 e mensagem informando que a quantidade excede o pedido, para todos os perfis.
- **Uma categoria por despesa:** a compra carrega uma única categoria financeira; gastos de categorias diferentes devem ser lançados separadamente.

## Resultado da implementação

- A compra do tipo **Despesa da empresa** aceita itens opcionais de materiais controlados no almoxarifado, com produto, SKU, descrição, unidade, quantidade e custo unitário; a categoria **Materiais de consumo e embalagem** está na lista de categorias.
- Recebimento total e parcial ficam disponíveis no detalhe da compra, com quantidade comprada, recebida, pendente e a deste recebimento; o saldo só muda na confirmação e a chave de idempotência por recebimento evita duplicidade em reenvio ou duplo clique.
- Produto ausente pode ser criado explicitamente no fluxo de recebimento e vinculado ao item; o vínculo não pode ser trocado depois do primeiro recebimento.
- Materiais de despesa só creditam itens do almoxarifado; peças para revenda mantêm o fluxo próprio de estoque e recebimento.
- Cada movimento de estoque registra compra, item, quantidade, autor e horário, e o evento fica no histórico da compra.

## Verificado em 11/10/2026

- `backend/app/api/routes/purchases.py`: `_apply_receipt` (recebimento total/parcial, idempotência, limite de quantidade, criação e vínculo de produto, `stock_type = warehouse` para despesa) e `_sync_payable`.
- `frontend/src/app/pages/purchases/purchases.ts`: campos de despesa (categoria, valor, condição de pagamento) e a seção "Materiais controlados no almoxarifado"; a lista de categorias inclui "Materiais de consumo e embalagem".
- `RELEASE_NOTES.md`: nota "Recebimento de materiais de despesas · 747227f" na seção de 9 de outubro de 2026.
- Nenhum trabalho novo é necessário para a P0. O que ficou fora do escopo original está registrado em specs próprias: devolução pontual ao fornecedor na P15 e contagem de estoque na P17; transferência entre almoxarifados e controle de lote seguem fora de escopo.
