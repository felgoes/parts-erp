# P0 — Receber itens de compras no almoxarifado

**Status:** em andamento — fluxo atual mapeado; spec ajustada para o modelo financeiro e de estoque
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

## Decisões a verificar no início da implementação

- Como o lançamento financeiro de despesas é exibido/registrado atualmente; preservar seu momento e garantir vínculo único à compra.
- O almoxarifado é único; não criar seleção nem suporte a múltiplos locais nesta tarefa. O saldo permanece associado ao produto.
- Campos obrigatórios para cadastro rápido de produto, conforme o cadastro padrão.
- Se o recebimento acima da quantidade comprada será permitido e por qual perfil.
- Se o usuário precisa lançar uma única compra com itens de categorias financeiras diferentes. A primeira versão considera uma categoria por despesa; nesse caso, separar em lançamentos por categoria.
