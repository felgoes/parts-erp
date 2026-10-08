# Parts ERP project rules

## Datas e fusos horários

- Toda data/hora recebida de marketplace, webhook ou dispositivo deve ser interpretada com o fuso informado pela origem.
- Persistir timestamps de operação em UTC, sempre com timezone explícito; nunca criar ou serializar `datetime` ingênuo.
- Respostas da API devem marcar timestamps UTC com `Z` (ou `+00:00`).
- A interface deve exibir datas operacionais no fuso `America/Sao_Paulo` (UTC−03:00), usando o locale `pt-BR`.
- Ao revisar uma tela, notificação, relatório ou histórico com data, verificar os três pontos: origem, persistência e apresentação. Adicionar teste para conversão quando houver risco de deslocamento.
