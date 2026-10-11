# P5 — Melhorar a visualização dos valores por item nos modais de compra

**Status:** implementado; validado manualmente em HML e implantado em PRD em 10/10/2026. Commit: `0987cd8`.
**Prioridade:** P5

## Objetivo

Melhorar visualmente os campos monetários associados a cada item nos modais de compra, para que o usuário consiga localizar, ler e editar o valor sem esforço ou corte do conteúdo.

## Escopo

- Revisar o modal de criação/edição de compra, incluindo as linhas de itens.
- Revisar o modal de detalhes da compra, incluindo edição do custo por item.
- Ajustar o campo de valor/custo unitário e, quando aplicável, os campos de frete, impostos e desconto por item.
- Melhorar largura, altura, tipografia, espaçamento, alinhamento, rótulo e estados de foco/erro conforme necessário.
- Garantir que o valor completo, incluindo `R$`, milhares e centavos, fique visível sem corte em desktop e celular.
- Manter os campos monetários ligados ao controle e à regra global de moeda da P1. Não criar uma máscara independente para Compras.

## Regras de interface

- O valor deve ser visualmente destacado e fácil de localizar em cada linha de item.
- Rótulos devem indicar claramente se o valor é custo unitário, frete, imposto ou desconto; não depender somente do placeholder.
- Largura e tamanho do texto devem acomodar valores monetários comuns com separador de milhares e duas casas decimais.
- Layout de desktop pode agrupar valores relacionados, mantendo cada campo distinguível.
- Em telas estreitas, os campos devem refluír para linhas/colunas legíveis; não comprimir o valor para caber junto de SKU e descrição.
- A interface deve indicar foco e erro sem depender apenas de cor, e manter alvos de toque confortáveis.
- Preservar cálculo, salvamento, permissões e semântica dos campos atuais.

## Critérios de aceite

1. Em ambos os modais de compra, cada campo de valor por item tem rótulo claro e tamanho legível.
2. Valores como `R$ 12.345,67` podem ser lidos por inteiro no campo sem rolagem horizontal ou caracteres cortados.
3. Campos de custo unitário, frete, impostos e desconto ficam visualmente associados ao item correto.
4. A apresentação continua organizada em desktop e em viewport móvel estreito, sem sobreposição ou controles inacessíveis.
5. O foco, seleção, edição e mensagens de validação permanecem visíveis e utilizáveis por teclado e toque.
6. A máscara e validação monetária são as mesmas do restante do ERP, conforme P1.
7. Valores salvos e totais calculados mantêm o comportamento atual.

## Fora de escopo

- Alterar regras de custo, rateio, impostos ou descontos.
- Mudar o modelo de dados ou criar novos campos financeiros.
- Redesenhar outros modais ou páginas sem relação com itens de compra.

## Verificação visual

Na implementação, revisar manualmente os dois modais em desktop e em viewport móvel estreito, usando um valor pequeno, um valor com milhares e centavos, e um valor longo próximo do limite aceito. Confirmar que o texto e o cursor não ficam cortados durante a edição.
