# P14 — Importação de documento de marketplace: conferência, moeda e leitura de itens

**Status:** pronta para implementação — decisões fechadas em 10/10/2026 sobre as amostras reais de AliExpress (duas), Alibaba e Mercado Livre (DANFE). Shopee sai do escopo até existir amostra.
**Prioridade:** P1

## Contexto

O ERP já importa documentos de compra desde a P3: o usuário escolhe o arquivo, o servidor identifica a plataforma, extrai campos e itens e devolve tudo para o modal "Revise antes de criar a compra". A revisão humana é obrigatória e nada é gravado antes da confirmação.

Com as amostras reais em mãos, a revisão do reconhecimento ficou concreta: o AliExpress funciona, o Alibaba vem pela metade e o Mercado Livre não entrega nada. Os problemas de fundo continuam os mesmos e são caros:

- **Valor em moeda estrangeira entra como se fosse real.** O leitor descarta o símbolo (R$, USD, US$) e devolve só o número; a compra é gravada em reais. No recibo da Alibaba isso acontece literalmente: o documento tem "Order total BRL 310.34" e "Order total in USD USD 58.00", e basta a ordem das linhas mudar para o ERP gravar R$ 58,00.
- **O valor efetivamente pago não é lido.** Na amostra da Alibaba o total do pedido é BRL 310,34, mas o valor pago é BRL 319,65 por causa da taxa de processamento. O ERP registra 310,34 e não avisa da diferença.
- **Item de documento em colunas não é lido.** É o formato de todos os recibos reais: no Alibaba e na DANFE, descrição, quantidade, valor unitário e total ficam em colunas, e o reconhecimento atual devolve zero itens. O usuário digita tudo à mão — o oposto do propósito de importar.
- **O mesmo pedido pode entrar duas vezes.** Nada compara o documento com as compras já registradas.
- **A conferência não confere.** O aviso atual compara a soma dos itens com o total ignorando frete, descontos e impostos, então quase sempre acusa diferença que não existe e não pega erro de verdade.
- **O usuário não vê o que foi lido** e a **confiança exibida é fixa** (78% nos campos, 58–62% nos itens), então não há como descobrir de onde veio um número errado nem onde olhar.

O resultado é dado errado entrando direto no custo, no estoque e no financeiro, com aparência de conferido.

## Diagnóstico nas amostras reais

| Documento | O que o ERP faz hoje | O que precisa mudar |
| --- | --- | --- |
| AliExpress — dois pedidos em imagem (28 set e 22 ago 2026) | Lê id do pedido, data, subtotal, descontos, frete, impostos e total, todos corretos; lê o item com descrição, valor e quantidade. A conta fecha: 214,40 + 37,03 + 50,31 − 96,71 = 205,03 | Nada estrutural. O "10PCS" do nome é o tamanho da embalagem e deve continuar na descrição — a quantidade comprada é o "x1". O valor pago e a forma de pagamento (Visa, Google Pay) ficam disponíveis para marcar "já pago" |
| Alibaba — recibo em PDF, uma página | Fornecedor e número do pedido vêm com o texto da coluna vizinha colado; a data "Oct 9th, 2026 (PDT)" não é lida; **nenhum item** é lido; o total é lido por sorte de ordenação das linhas | Cortar o valor na coluna do rótulo; aceitar data com mês antes do dia, ordinal e hora; ler os itens por coluna (qtd 20,00 · unitário BRL 6,43 · total BRL 128,42); priorizar a linha em BRL do total; ler a cotação que o próprio documento informa (1 USD = 5.350543 BRL); ler o valor pago (BRL 319,65) e avisar quando divergir do total; limpar entidades como `&amp;` |
| Mercado Livre — DANFE em PDF, uma página | **Não extrai nada**: nenhum campo, nenhum item, e a plataforma não é identificada | Ler a grade por coordenadas: chave de acesso (44 dígitos), Nº 003.178.655, SÉRIE 002, emitente STARHOUSE MEGA STORE LTDA, CNPJ 04.617.659/0001-42, data de emissão 25/09/2026, valor total dos produtos 29,90, frete 0,00, desconto 0,00, valor total da nota 29,90 e a linha do item (código 175461, Fita De Empacotamento 3m Scotch 5802 45mm X 45m 4 Rolos, UN, qtd 1, 29,90, 29,90) |

Duas observações que vieram das amostras e mudam decisões:

1. **A DANFE não traz a marca "Mercado Livre".** O que aparece é a transportadora EBAZAR.COM.BR LTDA. Para esse documento, a identificação automática pelo conteúdo não tem evidência suficiente: o caminho é a escolha do perfil na revisão, com sugestão a partir do nome do arquivo.
2. **A grade é o formato padrão, não a exceção.** Ler por coluna precisa valer para documento com texto (DANFE, Alibaba) e para imagem (OCR), não só para um dos dois.

## Objetivo

Fazer a importação de documento virar conferência em vez de digitação: ler os itens do recibo, mostrar de onde cada valor saiu, impedir que valor em outra moeda entre como real e não deixar o mesmo documento ser registrado duas vezes.

## Decisões de negócio (fechadas)

1. **Moeda estrangeira nunca entra 1:1.** O modal mostra a moeda lida no documento e exige a cotação usada. Sem cotação informada, não confirma.
   - Por quê: o custo da peça importada precisa estar em reais, e converter errado é pior do que não converter.
   - Alternativa descartada: converter automaticamente pela cotação do dia — mudaria o custo histórico sem o usuário saber a taxa aplicada.
2. **A cotação do próprio documento é aproveitada quando existir**, já preenchida e editável. Na amostra da Alibaba o recibo informa "1 USD = 5.350543 BRL".
   - Por quê: é a taxa que a plataforma realmente aplicou na cobrança.
   - Alternativa descartada: exigir digitação mesmo quando o documento já informa a taxa.
3. **Valor original, moeda e cotação ficam registrados** na compra, além do valor em reais.
   - Por quê: permite conferir depois contra a fatura do cartão e o extrato.
   - Alternativa descartada: guardar só o valor em reais — perderia a ligação com o documento.
4. **O valor efetivamente pago tem campo próprio e divergência é avisada.** Quando o valor pago for diferente do total do documento (taxa de processamento, por exemplo), a revisão mostra os dois e destaca a diferença.
   - Por quê: é o valor que saiu do caixa e o que compõe o custo real; na amostra da Alibaba a diferença é de R$ 9,31.
   - Alternativa descartada: usar sempre o total do pedido — esconde o custo da taxa.
5. **Pedido repetido é bloqueado.** A comparação usa a chave de acesso quando o documento tiver (DANFE) e, sem ela, o número do pedido junto com a origem. Se já existe compra ativa com essa identificação, a importação para e aponta a compra existente. Se a compra existente estiver cancelada, o sistema avisa e deixa continuar.
   - Por quê: duplicar compra duplica custo, estoque e título a pagar.
   - Alternativa descartada: apenas avisar e seguir — aviso em tela é ignorado e o dado ruim entra.
6. **A conferência de fechamento é explícita no modal:** itens + frete + impostos − descontos = total do documento, com a diferença calculada. Quando o documento traz subtotal, a soma dos itens é comparada a ele também.
   - Por quê: separa erro de item de erro de frete ou imposto, e é o que o usuário confere de verdade.
   - Alternativa descartada: aviso genérico de "confira os valores" — foi o que gerou alarme falso na tela atual.
7. **Os itens são lidos pela posição no documento**, agrupando as palavras por linha visual e por coluna (descrição, quantidade, valor unitário, total), tanto em PDF com texto quanto em imagem pelo OCR.
   - Por quê: é o formato real dos recibos, inclusive da DANFE.
   - Alternativa descartada: manter os dois padrões de linha — é o que devolve zero itens hoje.
8. **A quantidade vem do que o documento diz como quantidade.** "x1", "2 un" e "Qty: 2" são quantidade; texto de embalagem no nome do produto, como o "10PCS" da AliExpress, continua na descrição.
   - Por quê: no recibo real da AliExpress o "10PCS" é o tamanho da embalagem e a quantidade comprada é 1; transformar isso em quantidade multiplicaria o estoque por dez.
   - Alternativa descartada: tratar todo número seguido de "PCS" como quantidade — foi o caminho que a amostra reprovou.
9. **A quantidade é derivada quando o documento traz apenas valor unitário e total da linha**, com a origem da derivação visível na revisão.
   - Por quê: completa a leitura sem inventar dado.
   - Alternativa descartada: deixar a linha zerada e o usuário calcular.
10. **O produto é vinculado sozinho só quando há correspondência exata** de SKU ou código de barras no catálogo, sempre visível e removível na revisão.
    - Por quê: acerta o caso comum sem criar vínculo errado por semelhança de nome.
    - Alternativa descartada: casar por nome aproximado — gera vínculo silencioso errado.
11. **A compra só é criada com o documento anexado**, na mesma operação. Falha ao guardar o arquivo não deixa compra sem documento.
    - Por quê: compra importada sem o documento de origem perde o lastro e não pode ser conferida depois.
    - Alternativa descartada: criar a compra e anexar depois, como hoje — já existe o estado de compra sem anexo quando o envio falha.
12. **A confiança percentual fixa sai da tela.** Cada campo mostra a origem do dado (documento, XML de NF-e) e, quando vier de OCR, a qualidade da leitura.
    - Por quê: número fixo não informa nada e dá aparência falsa de precisão.
    - Alternativa descartada: recalibrar os percentuais — continuaria sendo estimativa sem significado.
13. **O texto lido pode ser visto, mas não é guardado no servidor.** A revisão oferece "ver o que foi lido" com o texto usado na análise.
    - Por quê: é o que permite entender um valor estranho e corrigir o perfil depois.
    - Alternativa descartada: guardar o texto junto da compra — acumularia dados pessoais e conteúdo de documento sem necessidade.
14. **A revisão escolhe o tipo do lançamento:** peças para estoque (padrão) ou despesa da empresa. Despesa exige categoria e valor total e dispensa itens.
    - Por quê: hoje a importação cria sempre "peças", então recibo de material de consumo, ferramenta ou frete não tem caminho.
    - Alternativa descartada: importar despesa como peça e corrigir depois — suja o estoque com item que não é estocável.
15. **Compra de marketplace já paga pode nascer com o título baixado**, com data e forma de pagamento lidas do documento quando existirem.
    - Por quê: nas plataformas o pagamento acontece no checkout; os recibos das amostras informam data e forma (Visa, Google Pay).
    - Alternativa descartada: deixar sempre em aberto — cria passivo fictício em toda compra de marketplace.
16. **O que não foi lido aparece como "não identificado" e vazio**, nunca como zero.
    - Por quê: zero é informação; vazio é ausência de leitura, e confundir os dois faz valor errado ser salvo sem ninguém perceber.
    - Alternativa descartada: preencher com zero e deixar o usuário notar.
17. **A identificação da plataforma continua vindo do conteúdo e, quando não houver evidência, o nome do arquivo sugere o perfil**, sempre com confirmação na revisão e com a seleção manual disponível.
    - Por quê: a DANFE do Mercado Livre não traz a marca da plataforma no documento, e a amostra mostrou que exigir evidência textual deixa esse caso sem nenhuma identificação.
    - Alternativa descartada: classificar a DANFE pela transportadora — EBAZAR.COM.BR LTDA é a logística, não garante que a compra seja do Mercado Livre.
18. **Perfil novo pode ser criado a partir da revisão.** Depois de corrigir um documento, o usuário salva os rótulos usados como perfil daquela loja, no mesmo formato declarativo que já existe.
    - Por quê: hoje só é possível criando JSON à mão, o que na prática ninguém faz.
    - Alternativa descartada: deixar como está e esperar que o usuário escreva o JSON.

## Escopo

Fase 1 — correção do que já existe:

- Leitura e exibição da moeda do documento; cotação obrigatória quando não for real, aproveitando a taxa informada no próprio documento; registro do valor original, da moeda e da cotação na compra.
- Campo e aviso de valor pago diferente do total do documento.
- Corte do valor na coluna do rótulo, para fornecedor e número do pedido não virem com o texto da coluna vizinha.
- Bloqueio de documento repetido por chave de acesso (DANFE) e, sem ela, por número do pedido e origem, com link para a compra existente.
- Conferência de fechamento no modal (itens, frete, impostos, descontos, total e diferença) e comparação com o subtotal quando lido.
- Fim do desconto somado duas vezes e do sinal invertido em valor negativo.
- Datas nos formatos "28 set, 2026", "Oct 9th, 2026 (PDT)", "28 de setembro de 2026", "25/09/2026" e ISO, sem deslocamento de dia.
- Normalização de entidades como `&amp;` em descrições.
- Campos não lidos exibidos como "não identificado".
- Origem do dado no lugar da confiança fixa.
- "Ver o que foi lido" na revisão.
- Anexo do documento na mesma operação que cria a compra.
- Correção da leitura da NF-e XML: totais vindos do total da nota, nunca de valores por item; CNPJ do emitente, série e número registrados.
- Sugestão de perfil pelo nome do arquivo quando o conteúdo não identificar a plataforma.
- Uso do subtotal lido, hoje extraído e descartado.

Fase 2 — leitura de itens:

- Leitura de itens por linha visual e coluna, tanto em PDF com texto quanto em imagem pelo OCR.
- Perfil de DANFE com os rótulos reais do documento: chave de acesso, número, série, emitente, data de emissão, valor total dos produtos, frete, desconto, valor total da nota e a linha de produto.
- Separação entre quantidade comprada e texto de embalagem no nome do produto.
- Derivação de quantidade a partir de valor unitário e total da linha.
- SKU e código de barras quando existirem no documento.
- Vínculo automático ao produto por SKU ou código de barras exato.
- Sugestão de linhas candidatas do texto quando nenhum item for reconhecido.
- Escolha do tipo do lançamento na revisão (peças ou despesa).
- Marcação de "já pago no checkout", criando o título baixado.

Fase 3 — aprendizado e volume:

- Salvar os rótulos revisados como perfil da loja, no formato de perfil existente.
- Fila de vários documentos analisados um por vez.
- Cobertura de teste por leiaute recebido, com pelo menos dois leiautes por plataforma.

Toda a spec respeita as regras do ERP: datas de calendário sem deslocamento de fuso, exibidas em America/Sao_Paulo; dinheiro em reais com duas casas e `Decimal` no backend; `appMoneyInput` para entrada de valores; revisão funcional em desktop e em tela móvel (~390×844).

## Critérios de aceite

Fase 1:

1. Documento com valor em outra moeda: o modal mostra a moeda lida junto do valor e mantém a confirmação bloqueada enquanto a cotação não for informada.
2. Quando o documento informa a taxa de conversão, ela vem pré-preenchida na revisão e pode ser corrigida.
3. Compra importada de documento em outra moeda guarda o valor em reais, a moeda original, o valor original e a cotação usada.
4. Documento em reais, como os recibos da AliExpress, não pede cotação e mantém o comportamento atual.
5. Valor pago diferente do total do documento aparece nos dois campos, com a diferença destacada.
6. Fornecedor e número do pedido do recibo da Alibaba são lidos sem o texto da coluna vizinha.
7. Existe compra ativa com a mesma chave de acesso ou com o mesmo número de pedido e a mesma origem: a importação é bloqueada com mensagem que identifica a compra existente e permite abri-la.
8. O documento repetido pertence a uma compra cancelada: o sistema avisa e permite continuar.
9. O modal mostra itens + frete + impostos − descontos e o total do documento, com a diferença calculada; diferença acima de R$ 0,05 é destacada.
10. Quando o subtotal é lido, como nos recibos da AliExpress e da Alibaba, a soma dos itens é comparada a ele, com o mesmo limite de R$ 0,05.
11. Documento cujos números fecham, como as duas amostras da AliExpress, não gera nenhum aviso de conferência.
12. As datas "28 set, 2026", "Oct 9th, 2026 (PDT)", "28 de setembro de 2026", "25/09/2026" e "2026-10-09" resultam na data de calendário correspondente, exibida sem deslocar o dia.
13. Descrição com `&amp;` é exibida com "&".
14. Campo não lido aparece como "não identificado" e vazio, e não como zero.
15. Cada campo mostra a origem do dado (documento ou XML) e, quando vier de OCR, a qualidade da leitura; nenhuma porcentagem fixa de confiança permanece na tela.
16. A revisão oferece "ver o que foi lido" com o texto usado na análise, e esse texto não fica guardado no servidor.
17. A compra importada só é criada depois de o documento ser anexado; falha no anexo não deixa compra sem documento.
18. NF-e XML: frete, desconto, imposto e total vêm do total da nota, não de valores por item; CNPJ do emitente, série e número ficam registrados na compra.
19. Desconto de linha e desconto geral não são somados duas vezes, e valor negativo no documento não vira positivo.
20. Documento sem evidência de plataforma, como a DANFE, apresenta a sugestão vinda do nome do arquivo e permite trocar o perfil manualmente.

Fase 2:

21. Recibo da Alibaba: fornecedor, número do pedido, datas, subtotal BRL 128,42, frete BRL 181,92 e total BRL 310,34 são lidos corretamente, e o total em dólar não é usado como total.
22. Recibo da Alibaba: o item é lido com quantidade 20,00, valor unitário BRL 6,43 e total BRL 128,42, com a descrição completa, incluindo a segunda linha do nome.
23. DANFE do Mercado Livre: chave de acesso, número 003.178.655, série 002, emitente STARHOUSE MEGA STORE LTDA, data de emissão 25/09/2026, valor total dos produtos 29,90, frete 0,00, desconto 0,00 e valor total da nota 29,90 são lidos corretamente.
24. DANFE do Mercado Livre: o item é lido com código 175461, unidade UN, quantidade 1, valor unitário 29,90 e total 29,90, com a descrição completa em duas linhas.
25. Recibo da AliExpress: a quantidade comprada é 1 e o "10PCS" permanece na descrição; nenhuma linha tem quantidade multiplicada pela embalagem.
26. Linha com valor unitário e total, sem quantidade explícita, tem a quantidade derivada e a origem da derivação visível na revisão.
27. SKU ou código de barras lido que corresponde exatamente a um produto do catálogo vincula o produto automaticamente, com o vínculo visível e removível.
28. Documento sem item reconhecido mostra as linhas candidatas do texto e permite marcar uma delas como item, preenchendo a linha.
29. A revisão permite escolher peças para estoque (padrão) ou despesa; despesa exige categoria e valor total e não exige itens.
30. Compra marcada como "já pago no checkout" nasce com o título a pagar baixado, com a data e a forma de pagamento informadas.

Fase 3:

31. Depois de revisar, o usuário salva os rótulos usados como perfil da loja, gerado no formato de perfil existente e aceito pela validação atual.
32. Vários documentos podem ser selecionados e são analisados em fila, um por vez, sem travar a tela.

## Fora de escopo

- Integração por API das plataformas (Mercado Livre, AliExpress, Alibaba, Shopee) para puxar a compra sozinha; é assunto de spec própria.
- **Shopee:** sem amostra, fica fora do desenvolvimento. Volta quando houver um recibo da plataforma.
- Cálculo detalhado de tributos de importação (ICMS, imposto de importação, taxa de despacho) linha a linha; o usuário informa o valor e o ERP rateia.
- Leitura de boleto, comprovante de pagamento ou extrato de cartão.
- Validação da NF-e na SEFAZ ou assinatura digital.
- Documento manuscrito e foto muito ruim de qualidade.
- Combinação artificial de mercadorias de pedidos diferentes em um único documento importado.

## Dependências e riscos

- Depende dos perfis da P3, do vínculo de itens importados da P6 e do título a pagar das P7 e P8.
- As amostras usadas na P3 e as recebidas agora não são versionadas (decisão correta daquela spec); ficam fora do Git e servem apenas para calibrar e testar.
- Risco: coordenadas variam com a resolução e a rotação do arquivo. Mitigar com testes por leiaute e com a revisão obrigatória, que continua sendo a palavra final.
- Risco: bloqueio de duplicidade dar falso positivo. Mitigar usando a chave de acesso como identificador quando existir e liberando o caso de compra cancelada.
- Risco: cotação informada ou lida errada. Mitigar mostrando valor original, moeda e cotação na conferência e no detalhe da compra.
- Risco: o "Nº 003.178.655" da DANFE ser confundido com número de pedido do marketplace. Mitigar tratando-o como número do documento fiscal e guardando a série junto.
- Risco: novo campo de origem da compra exigir migração. É a mesma decisão já tomada na P7 para número do pedido e data do documento em campos próprios.
- A cotação desta spec é dado do documento, não máscara de entrada: as regras de moeda da P1 e da P10 continuam valendo para os campos de valor.

## Referências de mercado

| Prática consolidada | Onde se vê | Decisão para o Parts ERP |
| --- | --- | --- |
| Digitalização de documento mostra a origem do valor lido e exige validação humana | Odoo (document digitization em contas a pagar) | Adotado: origem do dado, texto lido e revisão obrigatória |
| Conferência entre pedido, recebimento e documento antes de pagar | SAP Business One e Microsoft Dynamics 365 | Adotado em forma mínima: conferência de fechamento dentro da própria revisão |
| Frete e demais custos compõem o custo do item (landed cost) | NetSuite, Odoo | Adotado: rateio já existente, agora com conferência, moeda e valor pago corretos |
| Documento fiscal identificado pela chave de acesso, não pelo número solto | Prática de NF-e no Brasil | Adotado: chave de acesso como identidade do documento e do bloqueio de duplicidade |

## Faseamento

- **Primeira entrega — fase 1:** moeda com cotação obrigatória e aproveitada do documento, valor pago, corte por coluna, bloqueio de duplicidade, conferência de fechamento, datas, origem do dado, texto lido, anexo na mesma operação, sugestão de perfil pelo nome do arquivo e correção da NF-e XML. É o bloco que impede dado errado de entrar no custo e no estoque.
- **Fase 2:** leitura de itens por coluna em PDF e em imagem, perfil de DANFE, quantidade contra embalagem, derivação de quantidade, SKU e código de barras, vínculo automático, sugestão de linhas, tipo do lançamento e "já pago no checkout". É o bloco que acaba com a digitação manual e que destrava os documentos da Alibaba e do Mercado Livre, hoje sem item nenhum.
- **Fase 3:** perfil a partir da revisão, fila de documentos e cobertura de teste dos leiautes recebidos.
- A fase 3 depende de amostras adicionais por plataforma; as fases 1 e 2 estão cobertas pelas quatro amostras recebidas em 10/10/2026.
