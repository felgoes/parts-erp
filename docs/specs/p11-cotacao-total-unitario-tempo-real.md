# P11 — Cotação com total e custo unitário em tempo real

**Status:** concluída — decisões do PO fechadas em 10/10/2026 e implementadas; implantada em PRD no commit `35610c1` em 10/10/2026 (nota "Cotação com total e preço unitário em tempo real"), com site e ERP em HTTP 200
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
- **Frete, impostos e desconto:** o total informado é o valor final da proposta, já com acréscimos e desconto. O rateio calcula primeiro o líquido das peças (total − frete − impostos + desconto) e distribui esse líquido entre os itens.
- **Proposta impossível:** total menor que a soma dos acréscimos menos o desconto, ou custo unitário negativo resultante do rateio, sinaliza o erro e impede salvar a cotação.
- **Cotação já registrada:** editar uma cotação salva continua recalculando do mesmo jeito, preservando histórico e auditoria.

## Referência de mercado (ERP)

- **SAP:** o preço é composto por condições (preço bruto, desconto, frete, imposto) e o total é sempre derivado; não existe digitação de total no documento. Digitar o total é uma conveniência de negociação, não a fonte de verdade.
- **TOTVS, Omie e Bling:** a cotação é registrada item a item com preço do fornecedor, e o total é calculado. Fechar a compra por valor global, com rateio entre itens, é comum em lote ou kit.
- **Rateio no Brasil:** frete e descontos são rateados por valor (proporcional) ou por peso/quantidade. Proporcional ao valor é a regra mais aceita para custo de aquisição; por quantidade faz sentido em peças homogêneas.
- **Conclusão do benchmark:** o caminho unitário → total é o padrão dos ERPs; o caminho total → unitário é diferencial de negociação e precisa de base de rateio explícita para não produzir custo arbitrário.

## Impacto administrativo e fiscal

- **Base de rateio inexistente:** ratear proporcionalmente ao valor quando nenhum item tem preço é divisão por zero. O caminho total → unitário precisa de um substituto determinístico, como quantidade ou último custo conhecido do produto.
- **Custo e financeiro:** o rateio define o custo unitário que entra no estoque e o valor do título a pagar. Por isso a soma dos itens tem de fechar exatamente com o total, e a sobra de centavos precisa ser rastreável.
- **Conferência fiscal:** divergência de centavos entre soma dos itens e total é a causa mais comum de retrabalho na conferência da nota do fornecedor.
- **Cotação vencedora já aprovada:** mudar valor depois de aprovado ou pago altera custo médio e financeiro. A prática de mercado é bloquear ou exigir reescolha com registro de auditoria.

## Decisões fechadas

1. **O total digitado é o valor final da proposta**, já com frete, impostos e desconto, porque é o número que o fornecedor fecha e que o comprador tem em mãos. O rateio trabalha sobre o líquido das peças: `líquido = total − frete − impostos + desconto`, e depois distribui o líquido entre os itens.
2. **Rateio padrão é proporcional ao subtotal de cada item**, com o método por quantidade disponível na tela. Quando nenhum item tem preço informado, não existe base proporcional: os dois métodos caem para rateio por quantidade, que é determinístico.
3. **Cotação escolhida fica travada para edição.** Alterar valor de cotação vencedora muda custo de estoque e título a pagar; para mudar preço, registra-se uma nova cotação e escolhe-se de novo, mantendo o histórico.
4. **Desconto por linha não existe mais** (decisão da P9). O cálculo bidirecional considera apenas o desconto da cotação, sem risco de desconto em dobro.
5. **Sobra de centavos vai para o item de maior valor** da proposta; em caso de empate, o primeiro item da lista. O ajuste aparece no detalhe da cotação e nunca fica implícito.
6. **Proposta impossível não é salva.** Total menor que frete + impostos − desconto, ou rateio que resulte em preço negativo em algum item, sinaliza o erro com mensagem explicando o motivo.

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
8. Cotação já escolhida não pode ser editada; a tela oferece registrar uma nova cotação, preservando o histórico da anterior.
9. Nenhum item recebe preço negativo pelo rateio, e o motivo é explicado quando a proposta não fecha.

## Verificação

- Montar no HML local uma compra com pelo menos três peças de quantidades diferentes e registrar uma cotação pelos dois sentidos, conferindo item a item.
- Testar os dois métodos de rateio com valores que geram centavos quebrados e conferir o fechamento.
- Conferir a mesma tela em desktop e mobile.
