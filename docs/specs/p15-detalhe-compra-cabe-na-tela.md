# P15 — O detalhe da compra cabe na tela em qualquer largura

**Status:** entregue em 12/10/2026 no commit `f4990e7`, em PRD (smoke público ok no site e no ERP).
Conferido no HML medindo de 1920 a 380 px de largura, além da condição que reproduzia o defeito
(coluna lateral forçada a 200 px). Só apresentação: nenhum cálculo ou fluxo mudou.
**Prioridade:** média — a tela de conferência da compra ficava ilegível em janela normal.

## Objetivo

O painel de detalhe da compra (itens e recebimento, cotações e resumo lateral) precisa caber na
janela: sem barra de rolagem horizontal e sem conteúdo cortado — o resumo lateral é a única leitura
de fornecedor escolhido, valor acordado, parcelas e histórico da compra.

## Sintoma verificado (imagem enviada pelo operador)

- O painel de detalhe abria com barra de rolagem horizontal.
- O cartão "Resumo" era cortado na direita: os valores (`1`, `20`, `0`, `R$ 319,65`) sumiam atrás da
  barra e o nome do fornecedor aparecia pela metade ("Fornecedo docume").
- O mesmo podia acontecer em qualquer largura de janela, dependendo do tamanho de fonte do navegador.

## Causa

A coluna lateral e o cartão de dentro do modal eram dimensionados pelo `min-content` do conteúdo:
um texto sem ponto de quebra (nome do fornecedor vindo do documento importado) ou um botão com
rótulo fixo ("Registrar pagamento") aumentava a caixa além dos 270 px reservados para a coluna. Como
o cartão ficava na borda direita do modal, o excesso virava conteúdo inalcançável — a barra
horizontal aparecia e o resumo continuava cortado mesmo rolando.

## Decisões

1. **Coluna lateral e cartão não crescem:** a faixa usa `minmax(0, 1fr) minmax(0, 270px)` e o cartão
   do resumo, `minmax(0, 1fr)`, com `min-width: 0` nos itens que compõem a coluna.
2. **Texto do detalhe pode quebrar em qualquer ponto:** nome de fornecedor, descrição de peça,
   composição de custo e parcelas quebram dentro da caixa em vez de empurrar o modal.
3. **O preço unitário final da peça mantém o próprio tamanho** — quem cede espaço na linha do item é
   a descrição da esquerda, que já quebra em várias linhas.
4. **Botão do título a pagar** fica em uma linha no tamanho normal e só quebra se faltar espaço de
   verdade; nunca empurra o cartão.
5. **Nada é escondido para caber:** não há recorte por `overflow` no modal; o que não couber quebra.
6. **Faixas de largura preservadas:** 270 px de coluna lateral no desktop, 220 px até 850 px, uma
   coluna abaixo de 700 px, como já era.

## Critérios de aceite

1. Em 1920, 1440, 1100, 1024, 900, 850, 768, 700, 600 e 380 px, o modal não tem barra horizontal
   (`scrollWidth` igual à largura visível) e nenhum elemento passa da borda direita.
2. O cartão do resumo aparece inteiro, com todos os valores legíveis, inclusive com nome de
   fornecedor longo.
3. O cartão do resumo nunca é mais largo que a coluna lateral que o contém.
4. No celular o painel continua em uma coluna, sem sobreposição de rótulos e sem corte lateral.
5. Nenhuma mudança de cálculo, payload, permissão ou fluxo de recebimento.

## Verificação feita na entrega

- Medição no HML local de 1920 a 380 px: `scrollWidth` do modal igual à largura visível em todas, e
  nenhum elemento além da borda direita.
- Reprodução do defeito antes da correção com a coluna lateral forçada a 200 px (cartão ia a 232 px e
  o modal ganhava barra); depois da correção, a mesma condição fecha sem estouro.
- Conferência visual em desktop, tablet e celular, incluindo o cartão "Contas a pagar" com o botão
  "Registrar pagamento".

## Fora de escopo

- Redesenhar o resumo lateral, mudar a ordem das informações ou criar novas seções.
- Alterar cálculo, rateio, status, permissões ou o fluxo de recebimento.
- Revisar as demais telas do ERP (cada uma tem sua própria passada de leiaute).
