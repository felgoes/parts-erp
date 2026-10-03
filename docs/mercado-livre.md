# Integração com Mercado Livre

## Fluxo

1. Um administrador inicia o OAuth pelo ERP.
2. Access e refresh tokens são armazenados criptografados.
3. O Mercado Livre envia uma notificação de pedido.
4. A API valida segredo, aplicação, vendedor, tamanho e formato e coloca a sincronização na fila Redis.
5. O worker consulta o pedido diretamente na API oficial.
6. O SKU do item é associado ao produto local.
7. Quando o pagamento está aprovado, o ERP cria/confirma uma fatura e baixa o estoque.
8. Se ainda não houver nota, o worker solicita a emissão ao Faturador do Mercado Livre.
9. Quando a NF-e estiver autorizada, o worker consulta a nota por `order_id`, baixa XML/DANFE e os vincula à fatura.
10. Quando o envio estiver em `ready_to_ship/ready_to_print`, baixa a etiqueta PDF e a anexa à mesma fatura.

Todas as operações usam IDs externos únicos e chaves de idempotência. Uma notificação repetida não gera outra venda nem outra baixa.

## Decisões e limites

- O ERP não calcula tributos: ele apenas solicita a emissão ao Faturador do Mercado Livre.
- A emissão depende de o vendedor ter configurado corretamente o Faturador e os dados fiscais dos produtos.
- O download fiscal depende da conta estar habilitada no Faturador e de a nota estar autorizada.
- Pedidos com SKU ausente ou desconhecido são importados com erro de conciliação e não baixam estoque silenciosamente.
- O acesso a dados reais exige credenciais e consentimento de uma conta vendedora.

## Endpoints oficiais usados

- OAuth: `/oauth/token`
- Identidade: `/users/me`
- Pedido: `/orders/{order_id}`
- Nota por venda: `/users/{seller_id}/invoices/orders/{order_id}`
- Solicitar emissão: `POST /users/{seller_id}/invoices/orders`
- Documento fiscal: caminho `xml_location` ou `danfe_location` retornado pela consulta de nota
- Envio: `/shipments/{shipment_id}`
- Etiqueta: `/shipment_labels?shipment_ids={shipment_id}&response_type=pdf`

Documentação oficial: [gestão e consulta de notas fiscais](https://developers.mercadolivre.com.br/pt_br/obtendo-nota-fiscal), [pedidos](https://developers.mercadolivre.com.br/pt_br/gerenciamento-de-vendas) e [dados de faturação](https://developers.mercadolivre.com.br/pt_br/faturamento).
