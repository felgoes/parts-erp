# Especificação — importação de compras por documento

**Status:** implementação local validada em HML e dependências OCR provisionadas/testadas no S9; publicação em PRD pendente
**Tarefa:** Parts ERP — importação de compras por OCR
**Atualizado:** 2026-10-09

## 1. Objetivo

Permitir iniciar uma compra a partir de um documento fiscal ou comercial, extraindo fornecedor, itens, quantidades e valores para uma etapa de conferência. A compra só é persistida após confirmação explícita. O cadastro manual atual continua disponível e sem dependência do OCR.

[historical infra reference removed]

### Recomendação: Tesseract 5 + modelo português `tessdata_best`

[historical infra reference removed]

[historical infra reference removed]

[historical infra reference removed]

Para NF-e em XML, usar parser XML local, sem OCR. No teste sintético, o parser de referência em Python padrão leu 1.000 documentos de dois itens em aproximadamente 0,17 s (cerca de 5.900 documentos/s). Esse microbenchmark mede parsing estrutural, não valida todos os leiautes/esquemas reais da NF-e.

[historical infra reference removed]

[historical infra reference removed]
- Tesseract 5.5.3 foi instalado temporariamente no Termux e removido ao final; o teste não reiniciou nem alterou API, worker ou Nginx.
- Corpus local gerado para o teste: sete imagens sintéticas de DANFE, com texto limpo, inclinação, desfoque, JPEG, baixa resolução e duas versões pré-processadas. Não havia amostras fiscais/PDF apropriadas nos arquivos do repositório.
- `tessdata_fast` + PSM 6: 61/63 trechos esperados encontrados nas sete imagens; mediana 1,21 s e máximo 1,37 s por imagem. PSM 11 encontrou 56/63 e não foi mais rápido.
- Comparação pareada em cinco imagens: `tessdata_best` encontrou 44/45 trechos-chave e levou 2,14–2,56 s por imagem (média ~2,40 s; pico observado ~60,7 MiB); `tessdata_fast` encontrou 43/45 e levou 0,88–1,11 s (média ~1,03 s; pico observado ~52,4 MiB).
- Um teste apontou erros que não podem passar sem revisão: `42,75` foi lido como `42,15` e `171,00` apareceu como `17/1,00`. Soma divergente, campos numéricos com baixa confiança ou formatos inválidos precisam destacar/rejeitar a prévia e solicitar correção.
- A tentativa de instalar Poppler para testar PDFs digitalizados falhou porque o repositório Termux configurado retornou HTTP 404 para uma dependência. Portanto, a etapa de renderização PDF ainda precisa de prova técnica; imagem OCR foi testada, PDF não.
[historical infra reference removed]

Os modelos oficiais oferecem uma troca explícita entre velocidade e qualidade: a documentação do Tesseract descreve `tessdata_best` como mais lento e mais preciso e `tessdata_fast` como menor/mais rápido. A decisão por `best` é provisória e deve ser confirmada com documentos anonimizados reais. Fontes: [Tesseract — arquivos de dados dos modelos](https://tesseract-ocr.github.io/tessdoc/Data-Files) e [Tesseract — tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast).

### Limitações e salvaguardas da decisão

- Os resultados acima usam imagens sintéticas feitas com fontes legíveis. Não generalizar o percentual para notas reais, fotos inclinadas, impressões térmicas, tabelas densas, baixa luz ou documentos manuscritos.
- O OCR retorna texto/caixas e confiança, não a estrutura fiscal confiável. Linhas e valores devem passar por parser, validações e revisão.
[historical infra reference removed]
- A primeira rodada com documentos reais deve usar ao menos 20 amostras anonimizadas com verdade de referência. Se a acurácia observada for baixa, mostrar só rascunho parcial; não ampliar automaticamente a extração.

## 3. Escopo da primeira versão

### Incluído

- Entrada por **Importar documento** na tela Compras, além de **Nova compra** manual.
- Uma nota fiscal/fatura por importação, nos formatos PDF, JPG, JPEG e PNG; XML de NF-e como caminho estruturado sem OCR.
- Arquivo com até 15 MB, respeitando também o limite já aplicado aos anexos. Inicialmente limitar PDFs/imagens a 20 páginas por documento para controlar tempo e custo.
- Identificação dos principais dados de fornecedor, documento, itens e totais, com confiança por campo quando disponível.
- Revisão e edição de todos os valores antes de criar a compra.
- Persistência do arquivo original como anexo da compra confirmada.
- Reutilização do cadastro manual quando o arquivo for incompatível, ilegível ou quando a extração falhar.

### Fora da primeira versão

- Importação em lote de documentos ou múltiplas notas em uma compra.
- OCR automático de DOC/DOCX/XLS/XLSX; continuam podendo ser anexados pelo fluxo manual existente.
- Recebimento de estoque, aprovação de cotação, contabilização ou lançamento fiscal automático.
- Reconhecimento de comprovantes manuscritos e classificação livre de qualquer tipo de documento.
- Treino/fine-tuning de modelo próprio na primeira versão.

## 4. Fluxo de usuário

1. Usuário escolhe **Importar documento** e seleciona o arquivo.
2. Backend valida extensão, MIME real, tamanho, páginas e conteúdo; XML de NF-e segue o parser local. PDF/imagem entra na fila de processamento.
3. UI mostra progresso e permite cancelar antes da criação. Erros dão mensagem acionável e opção de continuar com compra manual.
4. Tela de revisão mostra o documento e formulário editável. Campos incertos, ausentes, inconsistentes ou abaixo do limiar de confiança ficam destacados; confiança não substitui a conferência humana.
5. Usuário confirma tipo do documento, fornecedor, itens, quantidades, unidades, SKU/GTIN e valores. Pode editar, adicionar ou remover linhas.
6. Ao selecionar **Criar compra**, servidor valida novamente os dados e a idempotência e cria o registro e o anexo numa única operação lógica.
7. A compra abre na tela de detalhe já existente. O usuário segue o fluxo normal para cotar, aprovar, pedir e receber conforme o caso.

Cadastro manual permanece alcançável em todos os estados, sem enviar documento a serviço externo.

## 5. Dados extraídos e persistidos

### Fornecedor e documento

- Nome/razão social;
- CNPJ/CPF, quando presente;
- número, série, chave de acesso da NF-e e tipo do documento, quando presentes;
- data de emissão e vencimento, quando explícitos;
- moeda, padrão BRL; não inferir vencimento, condição de pagamento ou moeda ausente.

### Itens

- descrição original;
- código do fornecedor/SKU e GTIN/EAN, quando disponíveis;
- quantidade, unidade, valor unitário e total da linha;
- desconto, quando individualizado;
- vínculo com produto do ERP, se houver correspondência exata.

### Totais

- subtotal, frete, impostos, descontos e total, apenas quando encontrados no documento;
- preservar valores decimais sem arredondamento silencioso; apresentar e interpretar formato brasileiro, como `1.234,56`.

Persistir campos fiscais em estrutura própria de importação/documento, vinculada à compra, em vez de colocar chave e número apenas em observações. Guardar também a origem do valor (XML, modelo OCR ou edição humana) e confiança retornada pelo Tesseract, para diagnóstico e melhoria; nunca usar esse dado para autoaprovar.

## 6. Regras de mapeamento para o modelo atual

O backend atual tem compra, itens, cotações e anexos, mas não tem objeto próprio de rascunho de importação nem metadados fiscais completos. A implementação deve introduzir uma entidade de importação temporária e persistir os dados fiscais sem deformar o modelo de cotações.

- Importar documento fiscal não equivale a aceitar cotação. Valores fiscais não devem ser gravados como cotação aprovada.
- Ao confirmar uma NF-e/fatura de compra, criar a compra no estado coerente com documento já emitido (`ordered` somente se o documento/tipo e a ação do usuário confirmarem compra realizada); não lançar recebimento nem estoque automaticamente.
- Uma cotação comercial importada não deve criar pedido/compra já ordenada. Na primeira versão, não oferecer esse tipo de documento como importação estruturada; manter a entrada manual.
- Mapear custos unitários, frete, impostos e descontos para os campos de compra/itens existentes apenas depois de validação e confirmar que a soma fecha com o total. Preservar o total/documento fiscal separado para auditoria quando os campos existentes não representarem exatamente o documento.
- Associar produto somente por SKU/GTIN exato e único. Correspondência aproximada é apenas sugestão visual; nunca selecionar sem ação do usuário.
- Itens sem SKU podem ser criados como linhas sem vínculo de catálogo se o modelo permitir; caso o schema atual exija SKU, ajustar o schema de criação para aceitar SKU vazio/nulo em importação e manter a edição manual disponível. Não inventar SKU.

## 7. Duplicidade, idempotência e integridade

- Detectar duplicata por chave de acesso NF-e; se não existir, usar combinação normalizada de CNPJ do fornecedor, tipo, número e série.
- Mostrar a compra/documento existente e bloquear nova criação por padrão quando a chave fiscal for idêntica. Permitir exceção somente por ação explícita com justificativa e trilha de auditoria.
- A confirmação deve usar uma chave idempotente persistida no servidor e transação que vincule compra, itens, metadados e anexo. Clique repetido/retry não pode duplicar a compra.
- Validar quantidades positivas, valores não negativos nos campos aplicáveis, limites de precisão, fornecedor existente/novo conforme fluxo atual e campos obrigatórios.
- Comparar soma das linhas + frete + impostos − descontos com subtotal/total do documento. Divergência acima de tolerância definida deve ser exibida e confirmada, nunca corrigida em silêncio.

## 8. Arquitetura e operação

- Rodar o Tesseract como processo local do worker no Termux. Invocar com argumentos separados (sem shell), caminho validado e timeout; não colocar OCR na thread da requisição web.
- Executar em ARQ/Redis com concorrência OCR inicial de 1 e `OMP_THREAD_LIMIT=2`; observar fila, memória livre, temperatura/energia e latência antes de aumentar concorrência.
- Instalar a versão ARM64 do pacote Termux e fixar o hash/versão do modelo de idioma no procedimento de release. Não versionar executável ou modelo binário no Git.
- Guardar `por.traineddata` localmente. Nenhuma chamada externa é feita durante o processamento e nenhum conteúdo sai do aparelho.
- Para PDF com texto nativo, extrair o texto localmente antes de recorrer ao OCR. Para PDF escaneado, renderizar uma página por vez em resolução inicial de 250 dpi e descartar a imagem temporária após OCR. Escolher e validar a biblioteca/ferramenta Termux de PDF antes da V1; o teste de instalação do Poppler não completou por indisponibilidade de uma dependência no repositório configurado.
- Reduzir/redimensionar apenas imagens abaixo da resolução alvo e corrigir orientação quando detectada. O teste sintético não mostrou ganho consistente com pré-processamento; não executar filtros caros em toda imagem por padrão.
- Fazer timeout, retry limitado para erro transitório de fila, limite de concorrência e limite de páginas. Falha recuperável deixa o cadastro manual disponível.
- Guardar arquivo original apenas no rascunho temporário e anexá-lo após confirmação; remover rascunhos abandonados depois de 24 horas, conforme a política local de anexos.
- Logs: ID de correlação, duração, páginas, estado e categoria de erro. Não registrar imagem, OCR completo, CNPJ, nomes, valores ou credenciais.
- Métricas locais: volume, páginas, falhas, latência, pico de memória medido por processo e taxa de correção por campo; não incluir conteúdo fiscal nas métricas.
## 9. Critérios de aceite

1. **Nova compra manual** permanece funcional independentemente do Tesseract e sem credenciais externas.
2. PDF pesquisável, PDF digitalizado, foto/imagem e XML de NF-e chegam à revisão editável; PDF deve passar por prova técnica no Termux antes da liberação.
3. Campos ausentes/incertos permanecem vazios ou destacados; nenhum dado é criado sem confirmação.
4. Usuário consegue corrigir fornecedor, documento, linhas, quantidade, unidade, produto e valores; itens sem código não recebem SKU inventado.
5. Valores brasileiros são interpretados corretamente e totais divergentes são apontados.
6. Documento fiscal duplicado é detectado; retries e clique repetido não geram duas compras.
7. Confirmação não movimenta estoque, não aprova cotação nem marca recebimento.
8. Arquivo inválido, ilegível, fora do limite, limite excedido ou falha no processamento local mostram erro útil e permitem usar cadastro manual.
9. Nenhum documento ou resultado OCR completo aparece em logs; segredo nunca chega ao navegador.
10. Testes cobrem parser NF-e, mapeamento, decimal pt-BR, duplicidade, idempotência, limites, confiança parcial e falhas/retries do worker.
11. Antes da liberação, avaliar ao menos 20 documentos anonimizados, incluindo XML, PDF digital, PDF escaneado e fotos. Relatar acurácia campo a campo para fornecedor, documento, total e campos críticos dos itens; definir limiar de aprovação após a amostra e corrigir campos que falhem. Como toda saída é revisada, não se exige preenchimento perfeito, mas nenhum erro pode passar silenciosamente como confirmado.
12. Validar visualmente em HML local com usuário QA, em desktop e mobile, antes de publicar; registrar os cenários e evidências de validação.

## 10. Plano de entrega

[historical infra reference removed]
2. Implementar parser de NF-e XML, entidade/estados de importação e deduplicação, sem depender de OCR para NF-e XML.
3. Integrar o worker ao Tesseract local, testar extração de PDF no Termux e definir a renderização segura de páginas.
4. Implementar tela de envio/revisão e confirmação, mantendo formulário manual.
5. Completar cobertura automatizada e validar visualmente no HML local com usuário QA em desktop/mobile.
[historical infra reference removed]

## 11. Decisões recomendadas para aprovação de produto

- Aprovar Tesseract local com `tessdata_best` para imagens, condicionado à validação com documentos anonimizados e à prova de renderização PDF no Termux.
- Priorizar NF-e/fatura; XML processado localmente; cotação comercial estruturada fica fora da V1. Não há tarifa por documento.
- Usar fila e rascunho temporário; somente a confirmação explícita cria compra.
- NF-e/fatura confirmada representa compra documentada, mas jamais recebimento de estoque automático.
- Exigir revisão humana para todos os campos antes da persistência.

## 12. Perfis por marketplace e captura inteligente

A primeira versão deve incluir perfis reconhecedores para AliExpress, Mercado Livre, Shopee, Amazon e Alibaba. Eles são regras versionadas de extração, não modelos treinados no recibo do usuário. Cada perfil combina sinais de identificação (marca, textos recorrentes, moeda, país e tipo de documento), nomes alternativos dos campos e regras para agrupar descrição, quantidade, preço unitário, descontos, frete e total. O motor também considera posição e alinhamento dos blocos quando o OCR fornecer coordenadas.

Um perfil cobre apenas as variantes de layout que foram observadas e testadas. A mesma loja pode emitir recibos diferentes conforme país, idioma, versão do aplicativo e formato de exportação. Portanto:
- manter variantes nomeadas por marketplace, país/idioma e tipo de documento;
- permitir que o administrador importe um pacote JSON de perfil validado pelo esquema da aplicação e associe amostras documentais para teste;
- não aceitar executáveis, scripts, expressões regulares sem limites ou templates capazes de acessar arquivos/rede; perfil contém somente dados e padrões declarativos limitados;
- permitir escolher manualmente o marketplace quando a detecção automática não tiver evidência suficiente;
- salvar uma correção como nova variante de perfil somente depois de confirmar o documento, sem aprender automaticamente dados pessoais ou valores;
- identificar o perfil selecionado e a variante na prévia para que o usuário possa trocar antes de confirmar.

A extração deve ser híbrida, em ordem:
1. Ler texto e metadados nativos do PDF antes de aplicar OCR.
2. Para XML fiscal, usar campos estruturados do XML.
3. Para imagem/PDF escaneado, usar Tesseract por+eng quando disponível, com tessdata_best, PSM 6 e saída TSV para coordenadas e confiança. Idiomas adicionais só entram quando o perfil/documento os indicar; isso evita custo constante sem benefício.
4. Normalizar Unicode, espaços, separadores decimais e moedas sem descartar o texto original.
5. Aplicar as regras do perfil para fornecedor, identificadores, data, itens e totais. Considerar linhas vizinhas e cabeçalhos de tabela, não apenas palavras isoladas.
6. Validar relação quantidade × unitário ≈ total da linha, subtotais, descontos, frete e total final. Discrepâncias elevam alerta e reduzem confiança; jamais alterar valores para forçar fechamento.
7. Apresentar valor original, valor interpretado, origem (texto PDF/XML/OCR/perfil/edição) e confiança por campo. Campos críticos sem confiança suficiente ficam vazios ou pendentes.

A confiança deve considerar evidências independentes: reconhecimento do perfil, confiança OCR do trecho, proximidade de rótulos, coerência de formato, associação à linha da tabela e reconciliação aritmética. Uma confiança alta não dispensa a revisão humana nesta versão. Perfil desconhecido não impede o fluxo: mostrar extração genérica parcial e pedir escolha/revisão. Não fabricar CNPJ, SKU, quantidade, moeda, fornecedor ou preço ausente.

Critérios adicionais:
- Para cinco marketplaces, fixture de testes por variante de layout/idioma e testes negativos cruzados para garantir que um recibo não seja classificado incorretamente como outro.
- O perfil deve reconhecer a origem e extrair apenas campos comprovados no documento; indicação de perfil nunca significa aprovação automática.
- A aplicação deve permitir substituir ou corrigir qualquer campo e indicar visualmente os alertas antes da confirmação.
- A validação de qualidade deve usar documentos reais anonimizados e verdade de referência; os documentos sintéticos servem para regressão, não para declarar acurácia de produção.


## 13. Estado da implementação (09/10/2026)

A V1 está implementada no checkout local e passou pela validação visual em HML local com a conta QA, em desktop e em 375 px. A imagem sintética de referência foi reconhecida com fornecedor, pedido, total e item; uma compra de teste confirmou rateio de frete e anexo, e foi cancelada após a validação. O fluxo manual de compras continua disponível. Há uma seção Configurações → Importação de documentos para baixar o modelo JSON, importar perfis declarativos e remover perfis personalizados.

O processamento atual é local, limitado a 15 MB e 10 páginas PDF. Usa XML estruturado para NF-e, texto local via Poppler em PDF pesquisável, e Tesseract (por+eng, PSM 6, dois threads) em fotos e PDFs escaneados. A extração roda fora do event loop e só um arquivo é processado por vez por processo de API. O perfil pode ser escolhido manualmente; a detecção automática exige evidência mais forte para evitar pré-seleção por frases genéricas. Todos os campos permanecem editáveis e a criação depende da confirmação do usuário.

A implementação ainda não cobre todas as garantias sugeridas acima: metadados fiscais e data/número do documento ficam nas observações da compra, não em uma entidade fiscal própria; a compra e o anexo são gravados em duas requisições; não há deduplicação fiscal nem chave idempotente; o parser de itens é conservador e genérico, não cobre todas as variações de recibos; e não foi validado com 20 documentos reais anonimizados. Os perfis incluídos identificam marketplaces e ajustam rótulos, mas não são modelos treinados nem garantem reconhecimento de qualquer leiaute.

[historical infra reference removed]