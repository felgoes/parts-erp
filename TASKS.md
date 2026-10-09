# Lista de tarefas — Parts ERP

## Pendentes

- [x] CONCLUÍDO — Adicionar a opção de manter a sessão ativa sem logout automático (“nunca deslogar”), com encerramento manual e revogação da sessão.

- [ ] Implementar alertas push de segurança e disponibilidade pelo Firebase: tentativas de login e acessos negados anormais, mudanças de usuários/permissões e arquivos críticos, queda/reinício de serviços, fila parada e recursos esgotando. Usar gravidade, deduplicação e intervalo entre alertas; incluir monitor externo para detectar queda total do aparelho/internet. Solicitado em 07/10/2026, após a auditoria de segurança das APIs e do código.

- [ ] Concluir os backups automáticos para o Google Drive: a tela de Configurações já permite salvar a política (frequência e retenção de até 30 dias), mas ainda faltam autorização segura da conta Google, rotina/agendador no servidor, remoção automática das cópias vencidas e teste de restauração. Confirmar que a solução permanece gratuita e não versionar credenciais nem tokens.

## Fila solicitada — 07/10/2026

- [x] [P0] CANCELADO — Preparar um APK de teste para Apple iPhone (iOS), definindo o fluxo de distribuição e os requisitos de assinatura da Apple.
- [x] [P1] CONCLUÍDO — Usar em todos os objetos sincronizados do Mercado Livre e Shopee os timestamps fornecidos pelas plataformas, sem substituir por horário local do ERP.
- [x] [P2] CONCLUÍDO — Confirmar se os webhooks chegam e são processados imediatamente, medindo recebimento, fila, processamento e atualização no banco.
- [x] [P3] CONCLUÍDO — Documentar como funciona o horário de atualização do rastreio exibido no pedido, visão geral, faturas e pedidos do Mercado Livre.

- [x] [P5] CONCLUÍDO — Melhorar a esteira de status de venda em todos os objetos e telas, separando pedido, pagamento, fiscal, etiqueta, expedição e entrega. Status sugeridos: Pedido recebido → Pagamento aprovado → Aguardando NF → NF emitida → Aguardando etiqueta → Etiqueta disponível → Pronto para envio → Despachado → Em trânsito → Saiu para entrega → Entregue → Finalizado, com ramificações para pagamento pendente, revisão, cancelado, devolvido e falha na entrega.
