# P9 — Compra pede peças e quantidades; valores somente nas cotações

**Status:** decidida — decisões do PO fechadas em 10/10/2026; pronta para implementação
**Prioridade:** P1

## Objetivo

No cadastro da compra de peças, registrar somente o que já se sabe no início da negociação: peças, quantidades e dados do pedido. Nenhum valor é digitado nesse momento, porque ainda não existe cotação. Custo unitário, frete, impostos, desconto e total nascem na cotação de fornecedor e passam a compra somente quando uma cotação é escolhida.

## História do usuário

Como comprador, quero cadastrar a compra apenas com as peças e quantidades que preciso, para não inventar preço antes de ouvir fornecedor e para ter um único lugar de verdade para valores: a cotação.

## Regra central

- Não existe digitação de valor monetário em peça de compra fora da cotação, em nenhuma tela, modal, edição em lote ou rascunho, para nenhum perfil.
- Sem cotação escolhida, o item aparece com custo pendente; a compra é válida sem custo.
- Com cotação escolhida, os valores dos itens são os da cotação vencedora e ficam somente para leitura.

## Referência de mercado (ERP)

- **SAP (MM):** a necessidade nasce como requisição de compra, sem preço; o preço entra na solicitação de cotação (RFQ) e é herdado pelo pedido de compra do fornecedor vencedor. Não se digita preço na requisição.
- **TOTVS Protheus (Compras):** solicitação de compra → mapa de cotação → pedido de compra, e o pedido herda o preço do fornecedor escolhido no mapa.
- **Omie, Bling e Tiny:** o pedido de compra aceita preço, mas a prática é registrar a proposta do fornecedor na cotação e herdar o valor; preço também pode vir de tabela de preços ou contrato de fornecimento.
- **Conclusão do benchmark:** manter um único lugar de verdade para o preço e herdar para o pedido é o padrão dos ERPs maduros. Digitar valor estimado direto no pedido é exceção justificada, não o caminho normal.

## Impacto administrativo e financeiro

- **Custo de aquisição e custo médio:** o valor que entra no estoque no recebimento é o da cotação vencedora, com frete, impostos e desconto rateados. Sem cotação escolhida não existe custo de aquisição, então o recebimento não pode gerar custo nem alimentar custo médio.
- **Contas a pagar:** o título a pagar só pode nascer quando existe valor, ou seja, depois da escolha da cotação e da aprovação. Compra sem cotação não gera título com valor inventado nem zerado.
- **Divergência cotação × nota fiscal:** no recebimento, o valor da nota do fornecedor é o que vale para o financeiro. Divergência entre cotação e nota precisa ser registrada e visível, nunca sobrescrita silenciosamente.
- **Risco de desconto em dobro:** desconto percentual por linha na compra somado ao desconto da cotação aplica desconto duas vezes no mesmo custo. Manter o desconto em um único lugar evita erro de custo e de título.

## Escopo

- **Cadastro da compra — Peças para estoque:** manter apenas produto/SKU, descrição, unidade, quantidade e os dados do cabeçalho (fornecedor, previsão desejada, número do pedido do fornecedor, data do documento, observações e documentos). Nenhum campo monetário. O texto de orientação atual ("Nesta etapa, informe somente as peças e quantidades") permanece.
- **Detalhe da compra — Peças em negociação/aprovada:** remover o editor de custo por item do cartão da peça ("Custo base", "Frete por item", "Impostos por item", "Desconto por item" e o botão "Atualizar custo"). Enquanto não houver cotação escolhida, o cartão mostra o custo como pendente, sem campos editáveis.
- **Após escolher a cotação vencedora:** base, frete, impostos, desconto e unitário final de cada item vêm da cotação e aparecem somente para leitura.
- **Concorrência:** a cotação continua sendo o único lugar de entrada de valores — custo unitário por item, frete, impostos, desconto, método de rateio, prazo e condição de pagamento.
- **Rascunho/edição de dados da compra:** as linhas continuam editáveis em descrição, SKU, unidade e quantidade, sem campo de valor. O desconto percentual por linha é removido junto com os demais valores.
- **Título a pagar:** a compra de peças sem cotação escolhida não gera título. O título passa a ser criado na aprovação, com o valor da cotação vencedora.
- **Recebimento:** se o valor da nota do fornecedor divergir do custo da cotação, o recebimento mostra a divergência e exige observação; o custo registrado não é sobrescrito em silêncio.
- **Dados históricos:** compras e itens já gravados continuam exibindo os valores existentes; nada é recalculado nem apagado em lote.

## Decisões fechadas

1. **Desconto por linha (%) sai.** Valor percentual de compra é valor: desconto pertence à cotação. Manter os dois aplicaria desconto duas vezes no mesmo custo. Se desconto por peça for necessário no futuro, ele entra no formulário de cotação, nunca no cadastro da compra.
2. **Revisão da importação de documento mantém os valores extraídos.** O documento enviado funciona como a cotação de origem daquela compra: os valores vêm do papel, passam por revisão humana antes de salvar e ficam registrados como origem do custo. A regra de "nenhum valor no cadastro" vale para a compra digitada, não para a leitura do documento.
3. **Despesa da empresa mantém o valor total e o custo unitário dos materiais.** Despesa não tem cotação de fornecedor e o valor total é a base do título a pagar.
4. **Título a pagar só nasce com valor.** Compra de peças sem cotação escolhida permanece sem título; a geração acontece na aprovação, com o total da cotação vencedora.
5. **Divergência cotação × nota é registrada, não corrigida em silêncio.** O valor da nota manda no financeiro e a diferença fica visível para conferência.
6. **Sem alçada por faixa de valor nesta fase.** A operação é pequena; os perfis atuais (admin, manager, operator) e o registro de auditoria cobrem o controle. A criação de alçada foi encerrada sem implementação e está registrada na lista de tarefas.

## Fora de escopo

- Mudar o cálculo de rateio de frete, impostos e desconto dentro da cotação, além do que a P11 define.
- Alterar preço de venda, custo de catálogo de produto e estudos de mercado.
- Migrar, apagar ou recalcular valores de compras e itens já existentes.
- Criar novos perfis de acesso ou alçada de aprovação por valor.
- Gerar parcelas do título a pagar a partir da condição de pagamento (P12).

## Critérios de aceite

1. É possível salvar uma compra de peças sem informar nenhum valor, e nenhum campo monetário aparece no cadastro.
2. No detalhe da compra, nenhum campo monetário é editável para peças; os valores por item aparecem somente depois de uma cotação escolhida e em modo leitura.
3. Sem cotação escolhida, a compra permanece válida com custos pendentes, sem valor inventado nem zero silencioso.
4. A tela de concorrência continua registrando custo unitário por item, frete, impostos, desconto e total da proposta.
5. Nenhum caminho de tela ou perfil permite alterar o custo de uma peça fora da cotação, e o desconto percentual por linha não existe mais.
6. A compra mantém o fluxo atual de aprovação, pedido ao fornecedor e recebimento; o estoque continua sendo alterado somente no recebimento.
7. Compra sem cotação escolhida não gera título a pagar; após a escolha e a aprovação, o título existe com o valor da cotação vencedora e sem duplicidade.
8. Recebimento com valor de nota diferente do custo da cotação exige observação e mostra a divergência; o custo original permanece rastreável.
9. A revisão da importação de documento continua permitindo conferir e corrigir os valores lidos do papel antes de criar a compra.
10. A despesa da empresa continua exigindo categoria e valor total, e continua gerando seu título normalmente.
11. Valores já gravados continuam exibidos e usados nos totais existentes.

## Verificação

- Percorrer o fluxo completo no HML local: criar compra de peças, conferir ausência de valor, conferir que não há título, registrar cotação, escolher vencedora, conferir valores por item, aprovar e conferir o título, receber com valor divergente do cotado.
- Conferir as telas em desktop e mobile, incluindo o cartão da peça sem cotação escolhida.
- Confirmar em banco que a compra sem cotação não criou custo fictício nem título, e que a aprovação gravou os valores e o título esperados.
