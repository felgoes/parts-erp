# P11 — Cotação com total e custo unitário em tempo real

**Status:** proposta — aguardando decisões do PO antes da implementação
**Prioridade:** P3

## Objetivo

Na cotação de fornecedor, poder informar tanto o valor total da proposta quanto o custo unitário de cada peça, sempre com o outro lado recalculado na hora. O comprador negocia por total com alguns fornecedores e por preço unitário com outros; hoje só o caminho unitário → total funciona.

## História do usuário

Como comprador, quero digitar o total que o fornecedor passou e ver o preço unitário de cada peça já calculado — e, quando o fornecedor passa preço por peça, ver o total — para comparar propostas sem fazer conta na mão.

## Comportamento esperado

- **Unitário → total (já existe, mantém):** informar o custo unitário de cada item recalcula o subtotal, aplica frete, impostos e desconto conforme o método de rateio e atualiza o total final da proposta imediatamente.
- **Total → unitário (novo):** o campo "Total final da proposta" passa a aceitar digitação. Ao informar o total, o valor é distribuído entre os itens conforme o método de rateio selecionado e o custo unitário de cada peça é atualizado na mesma hora.
- **Último campo manda:** o campo editado por último é a fonte da verdade; o outro é recalculado. Não pode haver recálculo em vaivém que faça o número digitado mudar sozinho.
- **Rateio:** no método proporcional, distribuir pelo subtotal atual de cada item; no método por quantidade, distribuir pela quantidade de peças. Empate ou subtotal zero tem regra explícita e determinística.
- **Fechamento de centavos:** a soma dos itens rateados tem de fechar exatamente com o total informado; a diferença de arredondamento é ajustada na última linha e visível para o usuário.
- **Frete, impostos e desconto:** o total informado é da proposta inteira, já com acréscimos e desconto, ou é o subtotal das peças antes deles? (decisão do PO — ver abaixo).
- **Proposta impossível:** total menor que a soma dos acréscimos menos o desconto, ou custo unitário negativo resultante do rateio, sinaliza o erro e impede salvar a cotação.
- **Cotação já registrada:** editar uma cotação salva continua recalculando do mesmo jeito, preservando histórico e auditoria.

## Pontos que precisam de decisão do PO

1. **O que o total digitado representa:** o valor final da proposta (peças + frete + impostos − desconto) ou o subtotal das peças, com frete, impostos e desconto somados depois? Isso define qual número o rateio usa por padrão.
2. **Sentido padrão com vários itens:** quando o total é digitado e nenhum item tem preço ainda, o rateio começa pelo método selecionado (proporcional/quantidade). Confirmar qual é o padrão sugerido na tela.
3. **Editar cotação já escolhida:** permitir recalcular a cotação vencedora depois de escolhida altera o custo do item e o título a pagar. Manter bloqueado, exigir reescolha ou permitir com aviso?
4. **Desconto por linha:** se o desconto percentual por peça permanecer (ver P9), informar como ele entra no cálculo bidirecional.
5. **Arredondamento:** ajustar a sobra na última linha por ordem de exibição está adequado, ou o ajuste deve ir para o item de maior valor?

## Fora de escopo

- Comparação automática de fornecedores, histórico de preços por fornecedor e negociação por e-mail/mensagem.
- Alterar o motor de rateio de frete, impostos e desconto já existente além do necessário para o cálculo bidirecional.
- Conversão de moeda, prazo de pagamento e cálculo financeiro de contas a pagar.

## Critérios de aceite

1. Com dois itens e quantidades conhecidas, digitar o total da proposta preenche o custo unitário de cada item na hora, e a soma dos itens fecha com o total digitado.
2. Digitar o custo unitário de um item recalcula o total final imediatamente, incluindo frete, impostos e desconto.
3. Alternar entre os dois campos não faz o valor digitado mudar sozinho; o último campo editado prevalece.
4. Trocar o método de rateio redistribui os valores coerentes com o novo método e mantém o total.
5. Proposta com total impossível (menor que os acréscimos menos o desconto) fica sinalizada e não pode ser salva, com mensagem explicando o motivo.
6. A diferença de arredondamento de centavos aparece ajustada e rastreável, sem sobra nem falta de centavos entre itens e total.
7. A cotação salva mantém os valores calculados após sair e voltar à tela.
8. Os cinco pontos de decisão acima estão resolvidos e registrados nesta spec antes de implementar.

## Verificação

- Montar no HML local uma compra com pelo menos três peças de quantidades diferentes e registrar uma cotação pelos dois sentidos, conferindo item a item.
- Testar os dois métodos de rateio com valores que geram centavos quebrados e conferir o fechamento.
- Conferir a mesma tela em desktop e mobile.
