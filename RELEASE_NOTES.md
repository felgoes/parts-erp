# Notas de atualização — Parts ERP

## 12 de outubro de 2026 — entregas confirmadas em PRD

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
