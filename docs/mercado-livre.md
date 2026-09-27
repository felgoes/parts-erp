# Integração com Mercado Livre

## Fluxo

1. Um administrador inicia o OAuth pelo ERP.
2. Access e refresh tokens são armazenados criptografados.
3. O Mercado Livre envia uma notificação de pedido.
4. A API valida o formato e coloca a sincronização na fila Redis.
5. O worker consulta o pedido diretamente na API oficial.
6. O SKU do item é associado ao produto local.
7. Quando o pagamento está aprovado, o ERP cria/confirma uma fatura e baixa o estoque.
8. Quando a NF-e estiver autorizada, o worker consulta a nota por `order_id`, baixa XML/DANFE e os vincula à fatura.

Todas as operações usam IDs externos únicos e chaves de idempotência. Uma notificação repetida não gera outra venda nem outra baixa.

## Decisões e limites

- O ERP não calcula tributos nem emite NF-e.
- A emissão continua no Faturador do Mercado Livre.
- O download fiscal depende da conta estar habilitada no Faturador e de a nota estar autorizada.
- Pedidos com SKU ausente ou desconhecido são importados com erro de conciliação e não baixam estoque silenciosamente.
- O acesso a dados reais exige credenciais e consentimento de uma conta vendedora.

## Endpoints oficiais usados

- OAuth: `/oauth/token`
- Identidade: `/users/me`
- Pedido: `/orders/{order_id}`
- Nota por venda: `/users/{seller_id}/invoices/orders/{order_id}`
- Documento fiscal: caminho `xml_location` ou `danfe_location` retornado pela consulta de nota

Documentação oficial: [gestão e consulta de notas fiscais](https://developers.mercadolivre.com.br/pt_br/obtendo-nota-fiscal), [pedidos](https://developers.mercadolivre.com.br/pt_br/gerenciamento-de-vendas) e [dados de faturação](https://developers.mercadolivre.com.br/pt_br/faturamento).
