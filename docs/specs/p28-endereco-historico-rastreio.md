# P28 — Endereço de destino e histórico de rastreio legível

**Status:** entregue em 24/10/2026 no commit `490e932a051ebd4c6f4dcb9b139ecf29af839cac`,
em PRD. Testes: 256 backend e 81 frontend, build de produção e HML em desktop e 390 px;
smoke público do site e do ERP respondeu HTTP 200.
**Prioridade:** média, solicitada pelo usuário em 24/10/2026.

## Objetivo

Mostrar no rastreio dos modais de pedidos o endereço de destino informado pelo Mercado Envios
e tornar a linha do tempo legível quando houver várias atualizações do mesmo status com
substatus diferentes.

## Escopo

- Extrair e formatar o endereço do destinatário da resposta de envio do Mercado Livre.
- Persistir o endereço formatado somente no payload interno do pedido, sem criar coluna ou
  expor dados adicionais do comprador.
- Expor o endereço no detalhe de rastreio das faturas e no modal equivalente do dashboard.
- Mostrar endereço e código de rastreio no modal de pedidos do marketplace.
- Agrupar atualizações consecutivas do mesmo status na linha do tempo, exibindo o estado mais
  recente, a contagem de atualizações e os substatus sob expansão.
- Manter o modal utilizável quando o Mercado Livre estiver temporariamente indisponível.
- Validar desktop e mobile com a conta de QA e massa isolada.

## Fora de escopo

- Alterar endereço, etiqueta ou pedido no Mercado Livre.
- Exibir nome, telefone ou outros dados pessoais do comprador.
- Expor IDs internos, coordenadas ou o payload técnico completo.
- Alterar os filtros ou a listagem de pedidos.

## Critérios de aceite

1. Um pedido com endereço no envio mostra o destino formatado no rastreio.
2. A linha do tempo não repete várias linhas do mesmo status; o agrupamento preserva os
   detalhes dos substatus em uma expansão.
3. Eventos de status diferentes continuam em ordem cronológica e não são mesclados.
4. Pedidos sem endereço exibem uma mensagem neutra, sem quebrar o modal.
5. A API continua respondendo se a consulta ao Mercado Livre falhar.
6. Testes de backend e frontend, build, HML, deploy e smoke público passam.

## Verificação entregue

- Extração dos formatos de endereço aceitos e ausência de dados coberta por testes.
- Agrupamento de status repetidos, eventos intercalados e tipos de evento distintos coberto
  por testes.
- Modais de faturas, dashboard e pedidos conferidos no HML em desktop e 390 px.
- Massa QA identificável removida após a validação.
- Suite completa: 256 testes backend e 81 frontend; build de produção aprovado.
- Deploy `490e932` em produção com smoke HTTP 200 no site e no ERP.
