# Notas de atualização — Parts ERP

A versão web é identificada pelo commit implantado. Cada entrada aponta para os commits correspondentes no GitHub. O histórico anterior foi reconstruído pelos commits disponíveis; as datas abaixo são datas dos commits e não afirmam uma data de publicação em produção quando ela não foi registrada.

## 9 de outubro de 2026 — entregas confirmadas em PRD

- [Máscara de valores em reais · abc8e26](https://github.com/felgoes/parts-erp/commit/abc8e26): campos monetários padronizados em reais, com validação de até duas casas decimais.
- [Recebimento de materiais de despesas · df975ea](https://github.com/felgoes/parts-erp/commit/df975ea): registre recebimentos parciais ou totais e acompanhe saldo e histórico no almoxarifado.
- [Importação de compras por documento · 381ba04](https://github.com/felgoes/parts-erp/commit/381ba04): extraia dados de recibos para revisão antes de criar uma compra.

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
