# Parts ERP — Notas da versao

## 5 de outubro de 2026 — candidata a publicacao

### Novidades

- Compras com negociacao de cotacoes, aprovacao, pedido ao fornecedor e recebimento conectado ao estoque.
- Estudos de mercado para organizar oportunidades de pecas, custos e fornecedores.
- Cadastro de produtos preparado para canais de venda e sincronizacao de anuncios.
- Devolucoes e cancelamentos acompanhados no historico do pedido e da fatura.
- Perfis de acesso por funcao e endpoints preparados para o aplicativo Android.
- Identidade da empresa personalizavel, com nome, logotipo e tema claro ou escuro.
- Paineis de vendas, financeiro e monitoramento com filtros de periodo.

### Seguranca e estabilidade

- Dependencias Angular e Python atualizadas para versoes corrigidas.
- Removidos valores estaticos de teste que pareciam credenciais; o historico foi verificado com uma excecao restrita a um falso positivo legado.
- Ajustada a visualizacao de custos de cotacao quando o usuario nao tem permissao para ve-los.

### Importante

- A tela permite configurar a politica de backup, mas a conexao com o Google Drive e o agendador ainda nao estao ativos. Esta versao nao executa backups automaticos para o Drive.
- A emissao de NF-e continua dependendo do emissor do Mercado Livre; esta versao nao promete emissao fiscal automatica.
