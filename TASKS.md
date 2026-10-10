# Lista de tarefas — Parts ERP

## Pendentes

- [ ] [P9] Compra pede peças e quantidades; valores somente nas cotações.
  Tirar a digitação de valor das peças fora da cotação, inclusive o editor de custo por item no detalhe da compra, e manter a cotação como único lugar de entrada. Três decisões abertas: desconto por linha no rascunho, revisão da importação de documento e valor total da despesa da empresa.
  Spec: docs/specs/p9-compra-valores-somente-em-cotacoes.md

- [ ] [P10] Máscara de valores forte, somente inclusão.
  Campo sempre no formato `R$ 0,00`, vírgula e separador de milhar intocáveis; digitar acrescenta dígito e apagar remove só o último dígito. Colar valor com `R$` continua funcionando. Substitui a parte de edição livre da P1.
  Spec: docs/specs/p10-mascara-valores-somente-inclusao.md

- [ ] [P11] Cotação com total e custo unitário em tempo real.
  Digitar o total da proposta distribui pelos itens e mostra o preço unitário; digitar o preço unitário atualiza o total na hora, com rateio e fechamento de centavos.
  Spec: docs/specs/p11-cotacao-total-unitario-tempo-real.md

## Concluídas

## Encerradas sem implementação

## Fila solicitada

---

Backlog limpo em 10/10/2026; itens anteriores concluídos, cancelados ou encerrados permanecem no histórico do Git.
