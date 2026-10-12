# P6 — Leiaute e legibilidade dos campos na revisão da importação

**Status:** entregue em 12/10/2026 no commit `6f597fc`, em PRD (smoke público ok no site e no ERP).
Conferido no HML com o recibo real que originou a spec: campos em grade com 16px entre linhas e
12px entre colunas (medidos na tela), valores em reais por inteiro, total da linha alinhado à
direita e vínculo do produto em faixa própria. A cópia de documentação entregue está em
`parts-erp/docs/specs/`.
**Prioridade:** média — usabilidade da conferência do documento (não muda cálculo).

## Objetivo

Corrigir o espaçamento e a leitura dos campos de item na revisão da importação. Hoje os rótulos se
colam uns nos outros, valores em reais aparecem cortados durante a conferência e os controles de
vínculo do produto ficam espremidos — justamente na tela em que a pessoa confere o documento linha a
linha antes de criar a compra que vira custo e título a pagar.

## Problemas verificados na tela (imagem enviada)

- Rótulos vizinhos na mesma linha visual: "Quantidade Valor unitário" e "Desconto da linha" colados,
  com o rótulo do total quebrando em "Total da / linha:".
- Campos monetários estreitos demais: o valor aparece truncado (`R$ 6,4…`, `R$ 0,0…`) em repouso e
  durante a edição, o que impede conferir o número lido do documento.
- Bloco de vínculo do produto sem respiro: linha de vínculo, "Remover vínculo", "+ Cadastrar produto"
  e o seletor de produto dividindo a mesma faixa estreita, com sobreposição visual.
- Faixa de custo final ("Custo final: R$ 15,53 / un." com base, frete, impostos e desconto) colada no
  bloco acima, sem separação entre campo editável e cálculo.

## Decisões de leiaute

1. **Campos da linha em grade:** quatro colunas em desktop largo — Quantidade · Valor unitário ·
   Desconto da linha · Total da linha —, duas colunas em tablet e uma abaixo de 600 px, nesta ordem.
2. **Espaçamento uniforme:** 16 px entre linhas de campos e 12 px entre colunas da mesma linha, em
   todos os breakpoints; nenhum par de campos fica mais próximo que isso.
3. **Rótulo sempre acima do campo**, alinhado à esquerda, em uma linha quando couber, sem quebra no
   meio da palavra e sem encostar no campo vizinho.
4. **Largura mínima dos campos monetários** para exibir `R$ 12.345,67` por inteiro com a máscara de
   valores do ERP: nada é cortado em repouso nem durante a digitação com o cursor no fim.
5. **Total da linha é leitura:** alinhado à direita do bloco, na mesma linha de base dos campos, sem
   quebra de rótulo e com o valor completo visível.
6. **Vínculo do produto em faixa própria:** busca, resultado selecionado, "Remover vínculo" e
   "Cadastrar produto" em linhas separadas, com largura suficiente e alvos de toque de pelo menos
   40 px de altura.
7. **Faixa de custo final separada**, valor final destacado e composição (base, frete, impostos,
   taxas extras e desconto) legível, separada do bloco de campos por espaçamento e não por encostar.
8. **Somente apresentação:** máscara, valores enviados, rateio, payload e regras de bloqueio ficam
   idênticos.
9. **Nenhuma linha é escondida ou comprimida** para caber: a lista rola normalmente e a revisão
   funciona com 1, 5 e 20 linhas.

## Casos de borda

- Valor longo próximo do limite aceito (`R$ 12.345.678,90`): o campo mantém o valor legível sem
  empurrar os vizinhos para fora da tela.
- Quantidade grande com decimais (`1234,567`): o campo de quantidade não invade o de valor unitário.
- Desconto da linha zerado e preenchido: mesma largura nos dois casos, sem salto de leiaute ao digitar.
- Linha com e sem produto vinculado: mesmo espaçamento, sem deslocar os campos de valor.
- Tela estreita (390 px) com teclado numérico aberto: campos acessíveis por rolagem, sem sobreposição
  de rótulos.
- Teclado: foco visível em todos os campos e botões, na ordem quantidade → valor unitário → desconto
  da linha → vínculo do produto.

## Fora de escopo

- Redesenhar o restante do ERP, a paleta, a tipografia global ou as outras telas de compra.
- Alterar a máscara de valores, o rateio, os cálculos ou os textos de erro e bloqueio.
- Criar o campo de taxas extras (P5) ou mudar o fluxo de confirmação da importação (entregue na P0).
- Preparar a revisão para impressão ou exportação.

## Critérios de aceite

1. Em 1280, 1024, 768 e 390 px, nenhum rótulo quebra no meio da palavra nem colide com o campo vizinho.
2. `R$ 12.345,67` aparece por inteiro nos campos de valor unitário, desconto da linha e taxas extras,
   em repouso e durante a digitação.
3. A distância entre campos vizinhos é constante (16 px entre linhas, 12 px entre colunas) em cada
   breakpoint, conferida na entrega.
4. "Total da linha" e a faixa de custo final aparecem sem quebra estranha, alinhados aos valores
   monetários e separados do bloco de campos.
5. "Remover vínculo" e "Cadastrar produto" ficam em faixa própria com o seletor de produto, sem
   sobreposição, com altura de toque confortável.
6. A revisão funciona com 1, 5 e 20 linhas sem comprimir campos nem esconder conteúdo.
7. Nenhuma mudança de cálculo, payload ou regra de bloqueio: só apresentação.
8. Foco, seleção e digitação continuam funcionando por teclado e a máscara de valores não muda.
9. A entrega inclui comparação antes/depois em desktop e em viewport móvel estreito.

## Verificação

- HML com um documento de 1 linha, um de 5 linhas e um de 20 linhas, em desktop e em 390 px.
- Digitar um valor longo em cada campo monetário e confirmar que nada é cortado nem desloca os campos
  vizinhos.
- Percorrer a revisão só com teclado (tabulação e foco visível) e repetir o teste da máscara.
