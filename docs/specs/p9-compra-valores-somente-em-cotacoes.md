# P9 — Compra pede peças e quantidades; valores somente nas cotações

**Status:** proposta — aguardando decisões do PO antes da implementação
**Prioridade:** P1

## Objetivo

No cadastro da compra de peças, registrar somente o que já se sabe no início da negociação: peças, quantidades e dados do pedido. Nenhum valor é digitado nesse momento, porque ainda não existe cotação. Custo unitário, frete, impostos, desconto e total nascem na cotação de fornecedor e passam a compra somente quando uma cotação é escolhida.

## História do usuário

Como comprador, quero cadastrar a compra apenas com as peças e quantidades que preciso, para não inventar preço antes de ouvir fornecedor e para ter um único lugar de verdade para valores: a cotação.

## Regra central

- Não existe digitação de valor monetário em peça de compra fora da cotação, em nenhuma tela, modal, edição em lote ou rascunho, para nenhum perfil.
- Sem cotação escolhida, o item aparece com custo pendente; a compra é válida sem custo.
- Com cotação escolhida, os valores dos itens são os da cotação vencedora e ficam somente para leitura.

## Escopo

- **Cadastro da compra — Peças para estoque:** manter apenas produto/SKU, descrição, unidade, quantidade e os dados do cabeçalho (fornecedor, previsão desejada, número do pedido do fornecedor, data do documento, observações e documentos). Nenhum campo monetário. O texto de orientação atual ("Nesta etapa, informe somente as peças e quantidades") permanece.
- **Detalhe da compra — Peças em negociação/aprovada:** remover o editor de custo por item do cartão da peça ("Custo base", "Frete por item", "Impostos por item", "Desconto por item" e o botão "Atualizar custo"). Enquanto não houver cotação escolhida, o cartão mostra o custo como pendente, sem campos editáveis.
- **Após escolher a cotação vencedora:** base, frete, impostos, desconto e unitário final de cada item vêm da cotação e aparecem somente para leitura.
- **Concorrência:** a cotação continua sendo o único lugar de entrada de valores — custo unitário por item, frete, impostos, desconto, método de rateio, prazo e condição de pagamento.
- **Rascunho/edição de dados da compra:** as linhas continuam editáveis em descrição, SKU, unidade e quantidade, sem campo de valor.
- **Dados históricos:** compras e itens já gravados continuam exibindo os valores existentes; nada é recalculado nem apagado em lote.

## Pontos que precisam de decisão do PO

1. **Desconto por linha (%) no rascunho:** hoje existe um campo de desconto percentual por peça, fora da cotação. Ele sai junto com os demais valores ou permanece como ferramenta de negociação? Se permanecer, como ele conversa com o desconto da cotação?
2. **Importação de documento:** a revisão da importação pede total do documento, frete, desconto, impostos e valor unitário por item extraídos do próprio documento. Manter a revisão como está (valores vêm do papel, não são digitados às cegas) ou tratar o documento importado como cotação e remover a digitação de total ali também?
3. **Despesa da empresa:** despesa não tem cotação de fornecedor e hoje pede "Valor total" e custo unitário dos materiais, que alimentam o título a pagar. A regra de "nenhum valor no cadastro" vale só para compra de peças, mantendo a despesa como está?

## Fora de escopo

- Mudar o cálculo de rateio de frete, impostos e desconto dentro da cotação, além do que a P11 define.
- Alterar preço de venda, custo de catálogo de produto, contas a pagar e estudos de mercado.
- Migrar, apagar ou recalcular valores de compras e itens já existentes.
- Mudar permissões/perfis de acesso.

## Critérios de aceite

1. É possível salvar uma compra de peças sem informar nenhum valor, e nenhum campo monetário aparece no cadastro.
2. No detalhe da compra, nenhum campo monetário é editável para peças; os valores por item aparecem somente depois de uma cotação escolhida e em modo leitura.
3. Sem cotação escolhida, a compra permanece válida com custos pendentes, sem valor inventado nem zero silencioso.
4. A tela de concorrência continua registrando custo unitário por item, frete, impostos, desconto e total da proposta.
5. Nenhum caminho de tela ou perfil permite alterar o custo de uma peça fora da cotação.
6. A compra mantém o fluxo atual de aprovação, pedido ao fornecedor e recebimento; o estoque continua sendo alterado somente no recebimento.
7. Valores já gravados continuam exibidos e usados nos totais existentes.
8. Os três pontos de decisão acima estão resolvidos e registrados nesta spec antes de implementar.

## Verificação

- Percorrer o fluxo completo no HML local: criar compra de peças, conferir ausência de valor, registrar cotação, escolher vencedora, conferir valores por item, aprovar, receber.
- Conferir as telas em desktop e mobile, incluindo o cartão da peça sem cotação escolhida.
- Confirmar em banco que a compra sem cotação não criou custo fictício e que a escolha da cotação gravou os valores esperados.
