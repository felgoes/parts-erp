# Notas de atualização — Parts ERP

## 16 de outubro de 2026 — entregas confirmadas em PRD

- [Copiar e excluir a partir do detalhe da compra · 8d45390](https://github.com/felgoes/parts-erp/commit/8d45390): no painel de detalhe da compra, "Copiar compra" (no cabeçalho) e "Excluir compra" (no resumo lateral) não faziam nada — o painel pedia a ação e a tela não recebia o pedido. Agora copiar abre o cadastro já preenchido com os dados da compra e excluir abre a confirmação com a lista do que será apagado junto (itens, títulos a pagar e histórico), buscando a compra completa antes de mostrar.

- [Cadastro de compra: despesa da empresa formatada · 1e77710](https://github.com/felgoes/parts-erp/commit/1e77710): com "Despesa da empresa" selecionada (categoria "Serviços", por exemplo), a parte da despesa aparecia desmontada — o título "Dados do gasto" ficava ao lado dos campos, "Materiais controlados no almoxarifado" encostava no texto de apoio e os campos da linha de material saíam espremidos em colunas estreitas. A grade de campos estava sendo aplicada na seção inteira em vez do bloco de campos. Agora a seção usa o estilo de seção compartilhado, a linha de material usa a mesma grade da linha de peça e o campo a mais da despesa (unidade antes da quantidade) ganhou largura própria. Só apresentação: nada de cálculo ou fluxo mudou.

- [Tela do aplicativo: puxar para atualizar, retomada e aviso de conexão · 7e50cd4](https://github.com/felgoes/parts-erp/commit/7e50cd4): no aplicativo, arrastar a tela para baixo não recarregava nada e a lista podia continuar mostrando número velho depois que o Android mandava o aplicativo para segundo plano. Agora puxar a tela para baixo (com a tela no topo) recarrega os dados da tela atual sem recarregar a página — filtro aplicado, posição da rolagem e o que está digitado continuam onde estavam — e trazer o aplicativo de volta para a frente recarrega os dados e reabre a atualização automática, mesmo quando o Android não avisa que a tela voltou. Se o servidor parar de responder, aparece uma faixa discreta com a hora da última atualização e o botão "tentar agora", que sai sozinha quando a conexão volta. A recarga automática espera enquanto existe documento lido na revisão da importação ou formulário alterado e não salvo.

- [Backup que avisa quando falha, guarda cópia no servidor e não insiste a cada minuto · 835d511](https://github.com/felgoes/parts-erp/commit/835d511): o backup automático vinha falhando desde 15/10 e ninguém era avisado — o ERP gravava o erro, mas a tela continuava mostrando a data do último backup concluído como se estivesse tudo em dia. Agora a falha chega como aviso para administrador e gerente (notificação no aplicativo e faixa dentro do ERP), com o motivo explicado em português — "a autorização do Google expirou, reconecte a conta", por exemplo — e um botão para reconectar. Além do aviso, toda execução passa a guardar uma cópia do banco no próprio servidor antes de tentar o Drive, então o dia tem backup mesmo com o Google fora do ar, e a limpeza por retenção vale para essas cópias e para os arquivos que os deploys deixam. A tela de backups mostra último sucesso, última tentativa e próximo previsto, com estado em português (em dia, atrasado, falhou), o lugar onde as cópias ficam e a orientação de manter a conta do Google Cloud fora do modo de teste. A conexão passa a ser conferida no momento em que é conectada e, depois de uma falha, o ERP tenta de novo em intervalo controlado em vez de bater no provedor a cada minuto. Observação: a reconexão da conta Google em produção é uma ação do operador.

- [Acabamento do backup no mesmo dia · 86ab819](https://github.com/felgoes/parts-erp/commit/86ab819): a data do último backup concluído das instalações que já existiam é preservada na virada (`31c8218`), recuperada do histórico de avisos quando o campo novo estava vazio (`5ab6616`); o aviso de atraso passou a mostrar também o último motivo registrado e a limpeza por retenção das cópias locais deixou de depender de o Drive responder (`86ab819`).

- [Cópia local do backup no lugar certo, com a validade valendo para toda a pasta · 2e2e0cc](https://github.com/felgoes/parts-erp/commit/2e2e0cc): as cópias do backup estavam sendo gravadas em `backend/data/backups` porque a rotina herdava o diretório de trabalho do servidor, enquanto os pacotes do deploy ficavam em `data/backups` — a limpeza de validade olhava para uma pasta e os arquivos do deploy viviam em outra (`9ad0d9b`). Agora cópia e limpeza acontecem na mesma pasta, e a janela de retenção vale para todo o conteúdo dela, inclusive os snapshots manuais que antes escapavam da regra (`2e2e0cc`). Nada é removido dentro do prazo: a limpeza acompanha a validade configurada e roda também quando o Google Drive está fora do ar.

## 12 de outubro de 2026 — entregas confirmadas em PRD

- [Detalhe da compra cabe na tela · f4990e7](https://github.com/felgoes/parts-erp/commit/f4990e7): o painel de detalhe da compra abria com barra de rolagem horizontal quando o nome do fornecedor era longo, e o resumo lateral ficava cortado na direita — os valores (quantidade de itens, unidades, valor acordado) sumiam atrás da barra. A coluna do resumo e os cartões do detalhe passaram a se ajustar à largura disponível, com o texto quebrando dentro do cartão em vez de empurrar o painel. O resumo aparece inteiro em qualquer largura de janela, do monitor grande ao celular, e o preço unitário da peça segue com o valor completo na ponta direita da linha.

- [Formatação dos modais de compra · 47b60aa](https://github.com/felgoes/parts-erp/commit/47b60aa): ao separar a tela de compras em componentes, parte do estilo ficou para trás — as etapas da compra viravam uma lista simples, o resumo e o histórico apareciam sem os cartões, a composição de custo da peça saía colada e a confirmação de exclusão perdia a formatação. Os estilos foram reunidos nas folhas compartilhadas e chegaram também os campos que nunca tinham formatação própria (observações, campos de despesa, observação de recebimento, dica de custo da cotação e linhas candidatas da importação). Só apresentação: nada de cálculo ou fluxo mudou.

- [Documento que fecha deixa de ser bloqueado na importação · 6f597fc](https://github.com/felgoes/parts-erp/commit/6f597fc): numa nota em que o fornecedor imprime o unitário arredondado (R$ 6,43) mas cobra o total exato da linha (R$ 128,42), a revisão recalculava 20 × 6,43 = 128,60 e acusava R$ 0,18 de diferença — bloqueando a importação de um documento que fecha. Agora o total impresso na linha manda no fechamento, e a conferência soma as taxas extras na linha de fechamento (que antes mostrava a diferença da própria taxa). Na mesma passada, o leiaute da revisão ficou legível: campos em grade com espaço constante, valores em reais aparecendo por inteiro durante a conferência (R$ 12.345,67 cabe), o total da linha alinhado à direita como leitura e o vínculo do produto em faixa própria.

- [Testes de compras e de importação divididos por assunto · 7d6fabf](https://github.com/felgoes/parts-erp/commit/7d6fabf): os arquivos de teste das compras (28 cenários) e da importação de documento (18 cenários) foram separados por assunto — recebimento, exclusão, rascunho, cotação, leitura de rótulos e confirmação da importação. Nenhum cenário mudou: é só organização, para achar e alterar um teste ficar mais direto.

- [Serviços de integração e telas divididos por assunto · a795b47](https://github.com/felgoes/parts-erp/commit/a795b47): a publicação de anúncios (Mercado Livre e Shopee), o pós-venda de devoluções e os estudos de mercado foram separados em partes menores, assim como as rotas de integração (Mercado Livre de um lado, Shopee do outro) e quatro folhas de estilo (financeiro, monitoramento, configurações e faturas). Sem mudança de comportamento: mesmas telas, mesmas rotas e os mesmos anúncios publicados.

- [Taxas extras na compra: pagamento, processamento e juros · 0ab48e9](https://github.com/felgoes/parts-erp/commit/0ab48e9): quando o fornecedor cobra uma taxa por fora do valor das peças (a taxa de processamento de pagamento, por exemplo), ela agora tem onde ser lançada — na cotação e na revisão do documento importado, com o texto de apoio explicando o que entra ali. A taxa soma no total e é rateada entre as peças junto com o frete, então o custo de cada peça passa a ser o que você realmente pagou por ela, e o título a pagar nasce pelo valor que saiu do caixa. A revisão da importação mostra o fechamento completo (itens + frete + impostos + taxas extras − desconto = total) e o detalhe da compra mostra a taxa na composição de cada peça. Ao ler um documento, o sistema reconhece os rótulos de taxa em português e inglês — "taxa de pagamento" deixa de ser confundida com imposto — e, quando não há rótulo mas o valor pago é maior que o total do pedido, a diferença aparece como sugestão para conferir, com um botão para usá-la; nada é aplicado sem a sua conferência.

- [Sincronização do Mercado Livre dividida · b217cf3](https://github.com/felgoes/parts-erp/commit/b217cf3): a rotina que conversa com o Mercado Livre (1.022 linhas) foi separada em cinco partes — leitura do pedido e dados de apoio, pedidos, documentos fiscais e automação, envio e etiquetas, e catálogo e estoque. Sem mudança de comportamento: os mesmos pedidos, notas e etiquetas são sincronizados.

- [Rotas de contas a pagar divididas · daaefd0](https://github.com/felgoes/parts-erp/commit/daaefd0): a rota de contas a pagar do servidor (726 linhas) foi separada em leitura (lista, relatório e exportação), ações (detalhe, ajuste e pagamentos) e as contas de data e faixa de atraso que as duas usam. Sem mudança de comportamento.

- [Modelos do ERP divididos por área · a9663c4](https://github.com/felgoes/parts-erp/commit/a9663c4): a lista de tabelas do sistema saiu de um arquivo de 753 linhas para arquivos por área (usuários e dispositivos, catálogo, vendas e estoque, compras e títulos, marketplaces com pós-venda e os tipos de situação), mantendo a mesma lista de importação para o resto do sistema. Sem mudança de comportamento.

- [Folhas de estilo grandes divididas · 5d010eb](https://github.com/felgoes/parts-erp/commit/5d010eb): os arquivos de estilo mais longos (global, compras, estudos de mercado, layout, catálogo, painel, produtos e marketplaces) passaram a ser carregados em partes, na mesma ordem e com o mesmo resultado na tela. Manutenção: cada pedaço de estilo fica no tamanho em que dá para ler de uma vez.

- [Leitura de documento e contratos da API divididos · 2ec139b](https://github.com/felgoes/parts-erp/commit/2ec139b): a leitura de documento de compra (1.213 linhas) foi separada em perfis e rótulos, dinheiro e datas, colunas e DANFE, itens, OCR e constantes; os contratos da API (1.174 linhas) foram separados por assunto (usuários, produtos, compras e títulos, clientes, faturas e pós-venda, estudos, painel, marketplaces e telemetria). Sem mudança de comportamento — a mesma leitura de documento e os mesmos campos de resposta.

- [Detalhe da compra separado da tela · c34b14d](https://github.com/felgoes/parts-erp/commit/c34b14d): a tela de compras terminou de ser dividida — o painel de detalhe (rascunho, itens e recebimento, cotações, resumo lateral, histórico e título a pagar) virou componentes próprios com o estado em serviços separados. A tela saiu de 2.019 para 393 linhas de código e de 2.075 para 276 linhas de template, ficando dentro do teto que o projeto usa para manter o código legível. Nada muda para quem usa: conferido abrindo uma compra, registrando recebimento e copiando o pedido.

- [Tela de compras dividida em partes menores · 6dabecd](https://github.com/felgoes/parts-erp/commit/6dabecd): a revisão da importação de documento, o cadastro de nova compra (inclusive copiar um pedido) e a confirmação de exclusão saíram de dentro do arquivo da tela e viraram componentes próprios, com o estilo compartilhado em um arquivo comum. Nada muda para quem usa: as telas ficaram do mesmo jeito, e a exclusão e a cópia — que podiam aparecer atrás do painel da compra — agora ficam sempre na frente. É manutenção: deixa a tela de compras bem menor e mais rápida de alterar.

- [Modelos e contratos do ERP divididos por assunto · f322882](https://github.com/felgoes/parts-erp/commit/f322882): as peças comuns dos modelos (identificador, marca de tempo, hora UTC) e os eventos de telemetria ganharam arquivos próprios, e os contratos da cotação de compra saíram do arquivo compartilhado de contratos. Sem mudança de comportamento.

- [Organização interna da área de compras na API · d2f050e](https://github.com/felgoes/parts-erp/commit/d2f050e): a rota de compras do servidor (1.725 linhas) foi separada por assunto — criação, itens e anexos, cotações, recebimento, ciclo de vida, contas a pagar e importação de documento — mantendo exatamente as mesmas rotas públicas. Sem mudança de comportamento.

- [Organização interna da área de compras no ERP · 226e635](https://github.com/felgoes/parts-erp/commit/226e635): a revisão de importação de documento ficou com o modelo e as contas de fechamento em um arquivo próprio (com testes), em vez de misturados às 2 mil linhas da tela de compras. Sem mudança de comportamento — é manutenção: fica mais rápido e mais seguro alterar qualquer ponto da conferência.

- [Limite de tentativas no login, com liberação pela tela de Usuários · 66a0ab5](https://github.com/felgoes/parts-erp/commit/66a0ab5): repetir senha errada passou a ter limite. Muitas falhas vindas do mesmo lugar barram temporariamente aquele acesso (a janela é de 5 minutos) e falhas na mesma conta apenas acrescentam uma pequena espera antes de checar a senha — quem sabe a senha continua entrando, e não existe bloqueio de conta. A tela de login avisa, com o tempo restante, quando o acesso está temporariamente barrado, e a tela de Usuários ganhou o cartão "Tentativas de login bloqueadas", onde o administrador vê o que está barrado e devolve o acesso com um clique, por origem ou por e-mail.

- [Número de fatura deixa de repetir · 5e87257](https://github.com/felgoes/parts-erp/commit/5e87257): a sequência de faturas (VEN-AAAA-NNNNNN) passou a continuar do maior número já usado. Duas faturas criadas no mesmo instante deixam de disputar o mesmo número — a segunda recebe o número seguinte — e apagar uma fatura não devolve mais o número dela para a próxima.

- [Leitura do XML da nota fiscal mais restrita · 31598c3](https://github.com/felgoes/parts-erp/commit/31598c3): a leitura do XML da NF-e na importação de compras passou a usar um leitor que recusa declarações externas ao documento antes de interpretar qualquer conteúdo, e o trecho ganhou módulo e testes próprios. Sem mudança na conferência: os mesmos campos e itens continuam sendo lidos.

- [Organização interna dos serviços da API do ERP · cb7c360](https://github.com/felgoes/parts-erp/commit/cb7c360): os serviços que o sistema usa para falar com a API foram separados por área (compras, produtos, faturas, financeiro, clientes, usuários, integrações e outras), mantendo a mesma lista de operações para as telas. Sem mudança de comportamento.

## 11 de outubro de 2026 — entregas confirmadas em PRD

- [Organização interna dos tipos do ERP · 0a9d864](https://github.com/felgoes/parts-erp/commit/0a9d864): a lista de tipos compartilhados do sistema foi dividida por área (compras, produtos, faturas, financeiro, catálogo, notificações e outras), deixando a manutenção mais direta. Sem mudança de comportamento.

- [Lista de compras filtra e pagina no servidor · de3c0c8](https://github.com/felgoes/parts-erp/commit/de3c0c8): buscar, trocar a etapa e mudar o período passaram a ser feitos no servidor, e a lista agora traz só a página que está na tela — não o acervo inteiro. Numa loja com 500 compras, a tela deixa de baixar cerca de 770 KB e passa a baixar cerca de 38 KB. Os cartões de resumo continuam mostrando o período escolhido.

- [Lista de compras mais leve · 7c233fb](https://github.com/felgoes/parts-erp/commit/7c233fb): a lista de compras passou a trafegar só o que ela mostra de cada peça — descrição, quantidade e recebido — em vez dos valores de custo, frete, impostos e desconto, que ficam na tela de detalhe. A resposta ficou 43% menor desde o início deste trabalho, o que deixa a tela mais rápida em lojas com muitas compras.

- [Venda e baixa de estoque à prova de clique duplo · f9018b5](https://github.com/felgoes/parts-erp/commit/f9018b5): confirmar ou cancelar a mesma fatura duas vezes ao mesmo tempo, ou receber a mesma notificação de pedido repetida, deixa de arriscar erro — a baixa de estoque e a confirmação acontecem uma única vez. É manutenção de confiabilidade, sem mudança de comportamento na operação normal.

- [Robustez das notificações dos marketplaces · 9275133](https://github.com/felgoes/parts-erp/commit/9275133): as notificações de pedido dos marketplaces passaram a ter limites de tamanho e de frequência e a ignorar repetições, para que um volume anormal não atrapalhe a sincronização das vendas. Também ficou registrado em código que o processamento nunca confia no conteúdo da notificação: ele sempre relê o pedido na plataforma.

- [Base de código no padrão do projeto · 55feda7](https://github.com/felgoes/parts-erp/commit/55feda7): o código passou a seguir a formatação que o repositório já declara (100 colunas, aspas simples) e o lint ficou limpo, de ponta a ponta. Sem mudança de comportamento — é manutenção: fica mais rápido e mais seguro revisar e alterar qualquer tela.

- [Telas de compras mais leves · df4b199](https://github.com/felgoes/parts-erp/commit/df4b199): a lista de compras passou a carregar só o que ela mostra — histórico, anexos e títulos a pagar são buscados no momento de abrir a compra, que passa a exibir sempre o estado atual. Internamente, os templates das telas saíram de dentro do código e viraram arquivos próprios, e os formulários de importação ganharam tipos nomeados: a manutenção fica mais simples, menor e mais segura.

## 11 de outubro de 2026 — entregas confirmadas em PRD

- [Compra importada entra como compra já feita · 25a365e](https://github.com/felgoes/parts-erp/commit/25a365e): ao confirmar a revisão de um documento, a compra nasce com a cotação do documento aceita, o pedido registrado e o título a pagar criado (à vista, vencimento em 30 dias corridos da data do documento), pronta para receber — sem cadastrar uma cotação manual só para destravar. A revisão mostra o custo final por peça, com base, frete, impostos e desconto rateados, e o fechamento `itens + frete + impostos − descontos = total`; a confirmação é bloqueada, com o motivo na tela, quando a soma não fecha, quando frete e impostos superam o total, quando o desconto passa do valor da linha e quando falta SKU ou produto na linha.

- [Recebimento e datas no detalhe da compra · 25a365e](https://github.com/felgoes/parts-erp/commit/25a365e): o resumo da compra não soma mais texto no lugar de números — o que travava a tela e impedia registrar o recebimento — e o vencimento do título aparece como a data combinada, sem pular um dia na conversão de fuso.

## 10 de outubro de 2026 — entregas confirmadas em PRD

- [Conferência da importação recalcula e explica o bloqueio · 28049d4](https://github.com/felgoes/parts-erp/commit/28049d4): ao corrigir total, frete, impostos, desconto ou qualquer item, a conferência recalcula na hora (com a comparação contra o subtotal do documento); quando o botão de confirmar está bloqueado, a revisão lista o motivo — produto sem vínculo, cotação ausente, valor inválido ou desconto maior que a linha — em vez de deixar você sem saber o que falta.

- [Escolher produto existente na importação · 1a17fbb](https://github.com/felgoes/parts-erp/commit/1a17fbb): cada item da revisão da importação tem, além da busca por nome/SKU/código de barras, um seletor com os produtos do catálogo — vincule com um clique e remova quando precisar.

- [Importação de documento: escolha do lançamento, já pago e linhas candidatas · 8b07f1c](https://github.com/felgoes/parts-erp/commit/8b07f1c): na revisão você escolhe se o documento entra como peças para estoque (padrão) ou como despesa da empresa, com categoria e valor total; marcando "já pago no checkout", a compra nasce com o título a pagar baixado, com a data e a forma de pagamento informadas; e quando nenhum item é reconhecido, a revisão lista linhas candidatas do documento para virar item com um clique.

- [Recibo em imagem e vínculo por SKU · d8f3bd1](https://github.com/felgoes/parts-erp/commit/d8f3bd1): o recibo fotografado do AliExpress passa a ser lido com o item, mantendo o texto de embalagem ("10PCS") na descrição e a quantidade comprada correta; quando a quantidade é deduzida, a revisão indica isso; e item cujo SKU ou código de barras bate exatamente com um produto do catálogo já entra vinculado, visível e removível.

- [Origem do dado, anexo na mesma operação e NF-e XML · d9db8f1](https://github.com/felgoes/parts-erp/commit/d9db8f1): a revisão da importação mostra de onde veio cada valor (documento, XML da NF-e ou OCR com a qualidade lida) em vez de porcentagens fixas; a compra importada é criada e anexada na mesma operação, então falha no anexo não deixa compra sem documento; e a NF-e XML passa a registrar CNPJ do emitente, série e número em campos próprios.

- [Leitura de recibo por coluna (Alibaba e DANFE) · bec502c](https://github.com/felgoes/parts-erp/commit/bec502c): os itens de recibos com colunas agora são lidos — descrição (inclusive em duas linhas), quantidade, valor unitário e total da linha, com código do produto e unidade; a DANFE passa a entregar chave de acesso, número, série, emitente, CNPJ, data de emissão, valor dos produtos, frete, desconto e total da nota.

- [Importação de documento: moeda, cotação, valor pago e conferência · 6e117ad](https://github.com/felgoes/parts-erp/commit/6e117ad): a revisão mostra a moeda lida e exige a cotação quando o recibo não é em reais, aproveitando a taxa que o próprio documento informa; o valor pago ganha campo próprio com a diferença destacada (na amostra Alibaba, a taxa de R$ 9,31 aparece em separado); a conferência fecha itens + frete + impostos − descontos − total, sem alarme falso quando os números batem; documento repetido é bloqueado por chave de acesso ou número do pedido com origem; datas em vários formatos e o texto lido ficam disponíveis na revisão.

- [Excluir compra pelos três pontos · 24983c7](https://github.com/felgoes/parts-erp/commit/24983c7): a ação agora está no menu de cada pedido e no detalhe, com confirmação mostrando número, fornecedor, valor e o que será apagado; a exclusão remove itens, cotações, anexos, histórico e título a pagar, devolve o estoque recebido por movimento de estorno e fica registrada na auditoria. Bloqueia quando há pagamento ao fornecedor ou quando o estorno deixaria saldo negativo, explicando o caminho correto.

- [Título a pagar parcelado pela condição combinada · 701bef8](https://github.com/felgoes/parts-erp/commit/701bef8): escolha à vista, 30 dias, 30/60, 30/60/90 ou uma condição própria na cotação e na despesa; o título a pagar nasce na aprovação já parcelado, com vencimento e valor por parcela, baixa parcela a parcela e mudança de condição recalculando apenas o que está em aberto.

- [Compras sem valor: o preço entra pela cotação · 35610c1](https://github.com/felgoes/parts-erp/commit/35610c1): a compra de peças nasce só com peças e quantidades; custo, frete, impostos e desconto entram na cotação do fornecedor e aparecem na peça somente para leitura depois da escolha.

- [Cotação com total e preço unitário em tempo real · 35610c1](https://github.com/felgoes/parts-erp/commit/35610c1): digite o total que o fornecedor passou e veja o preço de cada peça — ou o contrário; a sobra de centavos fica visível e a cotação escolhida fica travada para edição.

- [Digitação de valores sem quebra · 35610c1](https://github.com/felgoes/parts-erp/commit/35610c1): valor sempre no formato completo em reais, com vírgula, ponto de milhar e R$ intocáveis; digitar acrescenta dígito, apagar remove o último e colar um valor copiado da nota continua funcionando.

- [Contas a pagar como módulo · 2e5a0f7](https://github.com/felgoes/parts-erp/commit/2e5a0f7): nova área com todos os títulos de compras e despesas — resumo de em aberto, vencido e pago no período, aging por faixa de atraso, baixa parcial com histórico de cada pagamento, conciliação, filtros, relatório por fornecedor e por mês e exportação em CSV.

- [Edição do pedido de compra simplificada · bbb6fe9](https://github.com/felgoes/parts-erp/commit/bbb6fe9): edite fornecedor, previsão, observações, número do pedido e data do documento no rascunho, inclua ou remova peças (SKU pode ficar para depois), aplique desconto por linha, cadastre o fornecedor no próprio fluxo, veja o valor total com paginação na lista, exclua rascunhos em lote e acompanhe previsões vencidas.

- [Compras: exclusão e cancelamento seguros · 6527b74](https://github.com/felgoes/parts-erp/commit/6527b74): exclua pedidos em rascunho com registro de auditoria, cancele com motivo escolhendo o que fazer com o material já recebido, encerre o saldo pendente, receba tudo de uma vez e acompanhe o título a pagar gerado pela compra ou despesa — com baixa e estorno no cancelamento.

- [HML local em um comando · a7812dc](https://github.com/felgoes/parts-erp/commit/a7812dc): rotina de desenvolvimento que sobe API, ERP e login de QA com um comando e encerra tudo depois, sem tocar em serviços de outras sessões.

- [Digitação de valores em reais · 1ea5591](https://github.com/felgoes/parts-erp/commit/1ea5591): digite, corrija e cole valores em reais sem o cursor pular; a máscara pt-BR é aplicada ao sair do campo e valores com mais de duas casas decimais ficam sinalizados para correção.

- [Vínculo de produtos nos itens importados · 0ec83fe](https://github.com/felgoes/parts-erp/commit/0ec83fe): associe cada linha importada a um produto existente ou cadastre uma nova peça; descontos e valores seguem na compra revisada.
- [Custos por item nas compras · 0987cd8](https://github.com/felgoes/parts-erp/commit/0987cd8): campos monetários mais legíveis nos modais de compra, com valores completos e edição em coluna em telas estreitas.

A versão web é identificada pelo commit implantado. Cada entrada aponta para os commits correspondentes no GitHub. O histórico anterior foi reconstruído pelos commits disponíveis; as datas abaixo são datas dos commits e não afirmam uma data de publicação em produção quando ela não foi registrada.

## 9 de outubro de 2026 — entregas confirmadas em PRD

- [Instruções públicas de infraestrutura generalizadas · 7e08f44](https://github.com/felgoes/parts-erp/commit/7e08f44): referências específicas foram removidas dos documentos públicos, mantendo as instruções de operação e o wrapper de deploy.
- [Perfis de documentos AliExpress e Alibaba · bd7f1f4](https://github.com/felgoes/parts-erp/commit/bd7f1f4): reconhece os campos dos recibos enviados e mantém DANFE sem marca de marketplace para revisão manual.
- [Máscara de valores em reais · 6b90755](https://github.com/felgoes/parts-erp/commit/6b90755): campos monetários padronizados em reais, com validação de até duas casas decimais.
- [Recebimento de materiais de despesas · 747227f](https://github.com/felgoes/parts-erp/commit/747227f): registre recebimentos parciais ou totais e acompanhe saldo e histórico no almoxarifado.
- [Importação de compras por documento · 76948be](https://github.com/felgoes/parts-erp/commit/76948be): extraia dados de recibos para revisão antes de criar uma compra.

## Histórico reconstruído pelos commits

### 8 de outubro de 2026

- [Sessão persistente e notificações · 3d70ed1](https://github.com/felgoes/parts-erp/commit/3d70ed1): mantenha a sessão ativa no aplicativo e acompanhe o estado das notificações push.
- [Preferências de notificações · b05c9b8](https://github.com/felgoes/parts-erp/commit/b05c9b8): consulte o histórico e ajuste alertas por categoria.
- [Rastreio do Mercado Livre · a1b4b5b](https://github.com/felgoes/parts-erp/commit/a1b4b5b): horários de rastreio usam a data informada pela plataforma.
- [Documentos no Android · 9e85a1c](https://github.com/felgoes/parts-erp/commit/9e85a1c): abra documentos fiscais no navegador do aparelho.

### 7 de outubro de 2026

- [Etapas da venda · 39ca031](https://github.com/felgoes/parts-erp/commit/39ca031): acompanhe o pedido desde a aprovação até o envio e a entrega.
- [Backups no Google Drive · dc67e81](https://github.com/felgoes/parts-erp/commit/dc67e81): configure cópias automáticas e receba avisos de conclusão.
- [Webhooks e sincronização · bcc350d](https://github.com/felgoes/parts-erp/commit/bcc350d): processamento com tentativas e acompanhamento de pedidos do marketplace.
- [Aplicativo Android · eea4e5b](https://github.com/felgoes/parts-erp/commit/eea4e5b): distribuição de APKs com versões identificadas.

### 6 de outubro de 2026

- [Despesas e anexos · c45059e](https://github.com/felgoes/parts-erp/commit/c45059e): registre gastos operacionais e mantenha seus documentos junto à compra.
- [Cotações e custos · ede549f](https://github.com/felgoes/parts-erp/commit/ede549f): distribua frete, impostos e descontos pelos itens da compra e compare fornecedores.
- [Alertas de vendas · 609527f](https://github.com/felgoes/parts-erp/commit/609527f): receba notificações de vendas do marketplace no celular.
- [Acesso biométrico · 5ef50ea](https://github.com/felgoes/parts-erp/commit/5ef50ea): entre no aplicativo Android com biometria.

### 4 de outubro de 2026

- [Compras e indicadores de estoque · 6d1a47e](https://github.com/felgoes/parts-erp/commit/6d1a47e): organize compras e acompanhe indicadores financeiros do estoque.
- [Rastreio de vendas · 6a2a9a8](https://github.com/felgoes/parts-erp/commit/6a2a9a8): consulte eventos e documentos da venda em uma tela de detalhes.
- [Catálogo público · 2da4d58](https://github.com/felgoes/parts-erp/commit/2da4d58): apresente peças e anúncios em uma página pública.
- [Monitoramento · 3023fa9](https://github.com/felgoes/parts-erp/commit/3023fa9): acompanhe a disponibilidade da API, do banco e do catálogo.

### 3 de outubro de 2026

- [Sincronização inicial do Mercado Livre · 8a8b6bb](https://github.com/felgoes/parts-erp/commit/8a8b6bb): importe pedidos existentes e relacione anúncios ao estoque pelo SKU.
- [Gestão de usuários · 6003889](https://github.com/felgoes/parts-erp/commit/6003889): administradores podem atualizar os dados de acesso.

### 2 de outubro de 2026

- [Integração com Mercado Livre e Shopee · f30dd82](https://github.com/felgoes/parts-erp/commit/f30dd82): sincronize vendas e documentos recebidos pelas plataformas.
- [Aplicativo móvel · df75f80](https://github.com/felgoes/parts-erp/commit/df75f80): base Android e iOS para acessar o ERP.

### 26 de setembro de 2026

- [Primeira versão do Parts ERP · 202f1f1](https://github.com/felgoes/parts-erp/commit/202f1f1): cadastro de produtos, estoque, clientes e faturas.

## Próximas entregas

Após cada publicação em produção, esta página recebe uma nota curta com a data confirmada do deploy e o link do commit implantado.
