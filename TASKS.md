# Lista de tarefas — Parts ERP

## Pendentes

## Concluídas

- [x] [P9] Compra pede peças e quantidades; valores somente nas cotações.
  A compra de peças nasce sem nenhum campo de valor, sem editor de custo por item e sem desconto percentual por linha; cada peça recebe os valores da cotação vencedora, já rateados por frete, impostos e desconto, em modo leitura. A revisão da importação de documento continua trazendo os valores do papel.
  Spec: docs/specs/p9-compra-valores-somente-em-cotacoes.md

- [x] [P10] Máscara de valores forte, somente inclusão.
  Campo sempre em `R$ 0,00`, com vírgula, ponto de milhar e `R$` intocáveis; digitar acrescenta dígito e apagar remove só o último. Colar valor com `R$` continua funcionando. Campo opcional vazio permanece vazio e correção passa a ser reescrever o valor.
  Spec: docs/specs/p10-mascara-valores-somente-inclusao.md

- [x] [P11] Cotação com total e custo unitário em tempo real.
  Digitar o total final da proposta distribui o líquido pelos itens e mostra o preço unitário; digitar o preço unitário atualiza o total na hora. Rateio proporcional ao subtotal, com queda para quantidade quando não há preço; sobra de centavos no item de maior valor e cotação escolhida travada.
  Spec: docs/specs/p11-cotacao-total-unitario-tempo-real.md

## Encerradas sem implementação

- [x] ENCERRADA — Alçada de aprovação por faixa de valor. Avaliada na revisão de ERP e administração de 10/10/2026: a operação é pequena e os perfis existentes (admin, manager, operator) somados ao registro de auditoria cobrem o controle. Criar hierarquia de aprovação seria controle sem uso real; pode voltar ao backlog se o time crescer.

- [x] ENCERRADA — Condição de pagamento estruturada gerando parcelas do título a pagar (P12). Descartada a pedido do PO em 10/10/2026 junto com a limpeza do backlog; a condição da cotação segue como texto livre e o título continua com vencimento único.

## Fila solicitada

---

Backlog limpo em 10/10/2026; itens anteriores concluídos, cancelados ou encerrados permanecem no histórico do Git.
