# Notas de atualização — Parts ERP

## 10 de outubro de 2026 — entregas confirmadas em PRD

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
