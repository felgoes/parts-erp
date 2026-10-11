# P14 — Importação de documento de marketplace: conferência, moeda e leitura de itens

**Status:** pronta para implementação — fases 1 e 2 decididas em 10/10/2026. A fase 3 está especificada e depende das amostras reais dos leiautes para calibração.
**Prioridade:** P1

## Contexto

O ERP já importa documentos de compra desde a P3: o usuário escolhe o arquivo, o servidor identifica a plataforma, extrai campos e itens e devolve tudo para o modal "Revise antes de criar a compra". A revisão humana é obrigatória e nada é gravado antes da confirmação.

A revisão feita em 10/10/2026 no código, nos perfis e nos testes mostrou que o reconhecimento entrega o essencial para os leiautes já mapeados, mas atrapalha no uso real:

- **Valor em dólar entra como se fosse real.** O leitor descarta o símbolo da moeda (R$, USD, US$) e devolve só o número; o modal mostra tudo em reais e a compra é gravada em reais. Uma compra de USD 300 entra como R$ 300, e esse valor vira custo da peça e margem.
- **O mesmo pedido pode entrar duas vezes.** Nada compara o número do pedido lido com as compras já registradas.
- **O aviso de conferência não confere.** Ele compara a soma dos itens com o total ignorando frete, descontos e impostos, então quase sempre acusa diferença que não existe e não pega erro de verdade.
- **Item de recibo em colunas não é lido.** O reconhecimento aceita apenas dois formatos estreitos (o do AliExpress e um genérico que exige descrição, quantidade e preço na mesma linha). Recibo com colunas separadas não gera nenhum item, e o usuário digita tudo à mão — o oposto do propósito de importar.
- **O usuário não vê o que foi lido.** O texto do OCR não é mostrado nem guardado: quando um valor sai errado, não há como descobrir de onde veio.
- **A confiança exibida é fixa** (78% nos campos, 58–62% nos itens, multiplicada pela qualidade do OCR), então não indica onde olhar.

O resultado é dado errado entrando direto no custo, no estoque e no financeiro, com aparência de conferido.

## Objetivo

Fazer a importação de documento virar conferência em vez de digitação: ler os itens do recibo, mostrar de onde cada valor saiu, impedir que valor em outra moeda entre como real e não deixar o mesmo pedido ser registrado duas vezes.

## Decisões de negócio (fechadas)

1. **Moeda estrangeira nunca entra 1:1.** Ao ler moeda diferente do real, o modal mostra a moeda do documento e exige a cotação usada, informada pelo usuário. Sem cotação, não confirma.
   - Por quê: o valor da peça importada precisa estar em reais, e converter errado é pior do que não converter. A cotação é decisão do dono, não do leitor.
   - Alternativa descartada: converter automaticamente por cotação do dia — mudaria o custo histórico sem o usuário saber qual taxa foi usada.
2. **O valor original e a cotação ficam registrados** na compra, junto do valor em reais.
   - Por quê: permite conferir depois contra a fatura do cartão e o extrato, e resolve dúvida sobre o número que entrou no estoque.
   - Alternativa descartada: guardar só o valor em reais — perderia a ligação com o documento.
3. **Pedido repetido é bloqueado.** Se já existe compra ativa com o mesmo número de pedido e a mesma origem, a importação para e aponta a compra existente. Se a compra existente estiver cancelada, o sistema avisa e deixa continuar.
   - Por quê: duplicar compra duplica custo, estoque e título a pagar.
   - Alternativa descartada: apenas avisar e seguir — aviso em tela é ignorado e o dado ruim entra.
4. **A conferência de fechamento é explícita no modal:** itens + frete + impostos − descontos = total do documento, com a diferença calculada. Quando o documento traz subtotal, a soma dos itens é comparada a ele também.
   - Por quê: é a única forma de o usuário saber se a leitura fechou, e separa erro de item de erro de frete/imposto.
   - Alternativa descartada: aviso genérico de "confira os valores" — foi o que gerou aviso falso e desconfiança na tela atual.
5. **Os itens são lidos pela posição no documento**, agrupando as palavras por linha visual e por coluna (descrição, quantidade, valor unitário, total), aproveitando a informação de coordenadas que o OCR já produz.
   - Por quê: é o formato real dos recibos de marketplace e o que elimina a digitação manual.
   - Alternativa descartada: manter os dois padrões de linha — continuaria falhando no caso mais comum.
6. **Quantidade e unidade são separadas da descrição.** "10PCS", "2 un", "2x" e "Qty: 2" viram quantidade e unidade, não texto da peça.
   - Por quê: unidade colada na descrição quebra a busca de produto e a leitura do item na compra.
   - Alternativa descartada: deixar como está e o usuário corrigir — repete trabalho em toda importação.
7. **O produto é vinculado sozinho só quando há correspondência exata** de SKU ou código de barras no catálogo, sempre visível e removível na revisão.
   - Por quê: acerta o caso comum sem criar vínculo errado por semelhança de nome.
   - Alternativa descartada: casar por nome aproximado — gera vínculo silencioso errado.
8. **A compra só é criada com o documento anexado**, na mesma operação. Falha ao guardar o arquivo não deixa compra sem documento.
   - Por quê: registro de compra importada sem o documento de origem perde o lastro e não pode ser conferido depois.
   - Alternativa descartada: criar a compra e anexar depois, como hoje — já existe o estado de compra sem anexo quando o envio falha.
9. **A confiança percentual fixa sai da tela.** Cada campo passa a mostrar a origem do dado (documento, XML de NF-e) e, quando vier de OCR, a qualidade da leitura.
   - Por quê: número fixo não informa nada e dá aparência falsa de precisão.
   - Alternativa descartada: recalibrar os percentuais — continuaria sendo estimativa sem significado para o usuário.
10. **O texto lido pode ser visto, mas não é guardado no servidor.** A revisão oferece "ver o que foi lido", com o texto usado na análise, durante a revisão.
    - Por quê: é o que permite ao usuário entender um valor estranho e é o que permite corrigir o perfil depois.
    - Alternativa descartada: guardar o texto junto da compra — acumularia dados pessoais e conteúdo de documento sem necessidade.
11. **A revisão escolhe o tipo do lançamento:** peças para estoque (padrão) ou despesa da empresa. Despesa exige categoria e valor total e dispensa itens.
    - Por quê: hoje a importação cria sempre "peças", então recibo de material de consumo, ferramenta ou frete não tem caminho.
    - Alternativa descartada: importar despesa como peça e corrigir depois — suja o estoque com item que não é estocável.
12. **Compra de marketplace já paga pode nascer com o título baixado.** A revisão oferece "já pago no checkout", com data e forma de pagamento.
    - Por quê: nas plataformas o pagamento acontece no momento da compra; hoje o usuário cria a compra e registra a baixa manualmente.
    - Alternativa descartada: deixar sempre em aberto — deixa passivo fictício em toda compra de marketplace.
13. **O que não foi lido aparece como "não identificado" e vazio**, nunca como zero.
    - Por quê: zero é informação; vazio é ausência de leitura, e confundir os dois gera valor errado salvo sem perceber.
    - Alternativa descartada: preencher com zero e deixar o usuário notar.
14. **Perfil novo pode ser criado a partir da revisão.** Depois de corrigir um documento, o usuário salva os rótulos usados como perfil daquela loja, no mesmo formato declarativo que já existe.
    - Por quê: hoje só é possível criando JSON à mão, o que na prática ninguém faz.
    - Alternativa descartada: deixar como está e esperar que o usuário escreva o JSON.

## Escopo

Fase 1 — correção do que já existe:

- Leitura e exibição da moeda do documento; exigência de cotação quando não for real; registro do valor original, da moeda e da cotação na compra.
- Bloqueio de pedido repetido por número do pedido e origem, com link para a compra existente.
- Conferência de fechamento no modal (itens, frete, impostos, descontos, total e diferença) e comparação com o subtotal quando lido.
- Fim do desconto somado duas vezes e do sinal invertido em valor negativo.
- Datas nos formatos "Sep 28, 2026" e "28 de setembro de 2026", além dos que já funcionam, sem deslocamento de dia.
- Campos não lidos exibidos como "não identificado".
- Origem do dado no lugar da confiança fixa.
- "Ver o que foi lido" na revisão.
- Anexo do documento na mesma operação que cria a compra.
- Correção da leitura da NF-e XML: totais vindos do total da nota, nunca de valores por item; CNPJ do emitente, série e número registrados.
- Uso do subtotal lido (hoje é extraído e descartado).

Fase 2 — leitura de itens:

- Leitura de itens por linha visual e coluna, aproveitando as coordenadas do OCR.
- Separação de quantidade e unidade, incluindo "10PCS", "2 un", "2x" e "Qty: 2".
- Derivação de quantidade quando o documento traz apenas valor unitário e total da linha.
- SKU e código de barras quando existirem no documento.
- Vínculo automático ao produto por SKU ou código de barras exato.
- Sugestão de linhas candidatas do texto quando nenhum item for reconhecido.
- Escolha do tipo do lançamento na revisão (peças ou despesa).
- Marcação de "já pago no checkout", criando o título baixado.

Fase 3 — aprendizado e volume:

- Salvar os rótulos revisados como perfil da loja, no formato de perfil existente.
- Fila de vários documentos analisados um por vez.
- Calibração dos leiautes reais das quatro plataformas, com pelo menos dois leiautes por plataforma cobertos por teste.

Toda a spec respeita as regras do ERP: datas de calendário sem deslocamento de fuso, exibidas em America/Sao_Paulo; dinheiro em reais com duas casas e `Decimal` no backend; `appMoneyInput` para entrada de valores; revisão funcional em desktop e em tela móvel (~390×844).

## Critérios de aceite

Fase 1:

1. Documento com valor em outra moeda: o modal mostra a moeda lida junto do valor e mantém a confirmação bloqueada enquanto a cotação não for informada.
2. Compra importada de documento em outra moeda guarda o valor em reais, a moeda original, o valor original e a cotação usada.
3. Documento em reais não pede cotação e mantém o comportamento atual.
4. Existe compra ativa com o mesmo número de pedido e a mesma origem: a importação é bloqueada com mensagem que identifica a compra existente e permite abri-la.
5. O número de pedido repetido pertence a uma compra cancelada: o sistema avisa e permite continuar.
6. O modal mostra itens + frete + impostos − descontos e o total do documento, com a diferença calculada; diferença acima de R$ 0,05 é destacada.
7. Quando o subtotal é lido, a soma dos itens é comparada a ele, com o mesmo limite de R$ 0,05.
8. Documento cujos números fecham não gera nenhum aviso de conferência.
9. As datas "Sep 28, 2026", "28 set, 2026", "28 de setembro de 2026", "28/09/2026" e "2026-09-28" resultam na mesma data de calendário, exibida sem deslocar o dia.
10. Campo não lido aparece como "não identificado" e vazio, e não como zero.
11. Cada campo mostra a origem do dado (documento ou XML) e, quando vier de OCR, a qualidade da leitura; nenhuma porcentagem fixa de confiança permanece na tela.
12. A revisão oferece "ver o que foi lido" com o texto usado na análise, e esse texto não fica guardado no servidor.
13. A compra importada só é criada depois de o documento ser anexado; falha no anexo não deixa compra sem documento.
14. NF-e XML: frete, desconto, imposto e total vêm do total da nota, não de valores por item; CNPJ do emitente, série e número ficam registrados na compra.
15. Desconto de linha e desconto geral não são somados duas vezes, e valor negativo no documento não vira positivo.

Fase 2:

16. Recibo com descrição, quantidade, valor unitário e total em colunas separadas é lido com quantidade, valor unitário e total corretos em todas as linhas.
17. "10PCS", "2 un", "2x" e "Qty: 2" viram quantidade e unidade separadas, sem unidade colada na descrição.
18. Linha com valor unitário e total, sem quantidade explícita, tem a quantidade derivada e a origem da derivação visível na revisão.
19. SKU ou código de barras lido que corresponde exatamente a um produto do catálogo vincula o produto automaticamente, com o vínculo visível e removível.
20. Documento sem item reconhecido mostra as linhas candidatas do texto e permite marcar uma delas como item, preenchendo a linha.
21. A revisão permite escolher peças para estoque (padrão) ou despesa; despesa exige categoria e valor total e não exige itens.
22. Compra marcada como "já pago no checkout" nasce com o título a pagar baixado, com a data e a forma de pagamento informadas.

Fase 3:

23. Depois de revisar, o usuário salva os rótulos usados como perfil da loja, gerado no formato de perfil existente e aceito pela validação atual.
24. Vários documentos podem ser selecionados e são analisados em fila, um por vez, sem travar a tela.

## Fora de escopo

- Integração por API das plataformas (Mercado Livre, AliExpress, Alibaba, Shopee) para puxar a compra sozinha; é assunto de spec própria.
- Cálculo detalhado de tributos de importação (ICMS, imposto de importação, taxa de despacho) linha a linha; o usuário informa o valor e o ERP rateia.
- Leitura de boleto, comprovante de pagamento ou extrato de cartão.
- Validação da NF-e na SEFAZ ou assinatura digital.
- Documento manuscrito e foto muito ruim de qualidade.
- Reescrever os leiautes das plataformas sem amostra disponível.

## Dependências e riscos

- Depende dos perfis da P3, do vínculo de itens importados da P6 e do título a pagar das P7 e P8.
- **Amostras reais**: as amostras usadas na P3 não estão versionadas (decisão correta daquela spec) e não estão disponíveis no ambiente. A fase 1 e a fase 2 podem ser implementadas e testadas com fixtures sintéticas; a calibração da fase 3 e a garantia de acerto campo a campo exigem as amostras de novo.
- Risco: coordenadas do OCR variam com a resolução e a rotação do arquivo. Mitigar com testes por leiaute e com a revisão obrigatória, que continua sendo a última palavra.
- Risco: bloqueio de duplicidade dar falso positivo. Mitigar casando número do pedido junto com a origem e liberando o caso de compra cancelada.
- Risco: cotação informada errada. Mitigar mostrando o valor original e a cotação na conferência e no detalhe da compra.
- Risco: novo campo de origem da compra exigir migração. É a mesma decisão já tomada na P7 para número do pedido e data do documento em campos próprios.

## Referências de mercado

| Prática consolidada | Onde se vê | Decisão para o Parts ERP |
| --- | --- | --- |
| Digitalização de documento mostra a origem e o valor lido e exige validação humana | Odoo (document digitization em contas a pagar) | Adotado: origem do dado, texto lido e revisão obrigatória |
| Conferência de três vias entre pedido, recebimento e documento | SAP Business One e Microsoft Dynamics 365 | Adotado em forma mínima: conferência de fechamento dentro da própria revisão |
| Frete e outros custos compõem o custo do item (landed cost) | NetSuite, Odoo | Adotado: rateio já existente, agora com conferência e com moeda correta |

## Faseamento

- **Primeira entrega — fase 1:** moeda com cotação obrigatória, bloqueio de pedido repetido, conferência de fechamento, datas, "não identificado", origem do dado, texto lido, anexo na mesma operação e correção da NF-e XML. É o bloco que impede dado errado de entrar.
- **Fase 2:** leitura de itens por coluna, quantidade e unidade, SKU e código de barras, vínculo automático, sugestão de linhas, tipo do lançamento e "já pago no checkout". É o bloco que acaba com a digitação manual.
- **Fase 3:** perfil a partir da revisão, fila de documentos e calibração dos leiautes reais.
- A fase 3 só começa com as amostras reais em mãos; as fases 1 e 2 não dependem delas.
