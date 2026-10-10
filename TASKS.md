# Lista de tarefas — Parts ERP

## Pendentes

- [ ] [P9] Compra pede peças e quantidades; valores somente nas cotações.
  Remover a digitação de valor das peças fora da cotação, inclusive o editor de custo por item no detalhe da compra e o desconto percentual por linha. Título a pagar só nasce com cotação escolhida e aprovação; divergência entre nota e cotação é registrada. Importação de documento e despesa da empresa mantêm seus valores.
  Spec: docs/specs/p9-compra-valores-somente-em-cotacoes.md

- [ ] [P10] Máscara de valores forte, somente inclusão.
  Campo sempre em `R$ 0,00`, com vírgula, ponto de milhar e `R$` intocáveis; digitar acrescenta dígito e apagar remove só o último. Colar valor com `R$` continua funcionando. Campo opcional vazio permanece vazio e correção passa a ser reescrever o valor.
  Spec: docs/specs/p10-mascara-valores-somente-inclusao.md

- [ ] [P11] Cotação com total e custo unitário em tempo real.
  Digitar o total final da proposta distribui o líquido pelos itens e mostra o preço unitário; digitar o preço unitário atualiza o total na hora. Rateio proporcional ao subtotal, com queda para quantidade quando não há preço; sobra de centavos no item de maior valor.
  Spec: docs/specs/p11-cotacao-total-unitario-tempo-real.md

- [ ] [P12] Condição de pagamento da cotação gera as parcelas do título a pagar.
  Trocar o texto livre "30/60 dias" por condição estruturada e criar o título parcelado na aprovação, com vencimentos, soma fechando no total e baixa por parcela.
  Spec: docs/specs/p12-condicao-pagamento-parcelas-titulo.md

## Concluídas

## Encerradas sem implementação

- [x] ENCERRADA — Alçada de aprovação por faixa de valor. Avaliada na revisão de ERP e administração de 10/10/2026: a operação é pequena e os perfis existentes (admin, manager, operator) somados ao registro de auditoria cobrem o controle. Criar hierarquia de aprovação seria controle sem uso real; pode voltar ao backlog se o time crescer.

## Fila solicitada

---

Backlog limpo em 10/10/2026; itens anteriores concluídos, cancelados ou encerrados permanecem no histórico do Git.
