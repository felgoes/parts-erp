# Lista de tarefas — Parts ERP

## Pendentes

## Concluídas

- [ ] [P1] Expurgar objetos históricos órfãos ainda servidos pelo GitHub após a reescrita das branches; solicitar limpeza hospedada ao suporte. Bloqueio: API ainda responde HTTP 200 ao SHA antigo. Spec: docs/specs/p4-generalizar-referencias-publicas-infra.md.


- [x] [P4] CONCLUÍDO — Generalizadas as instruções públicas e os registros OCR para omitir o identificador do checkout privado e dados do aparelho de produção; preservado o contrato do wrapper. Commit 7e08f44 implantado em PRD em 09/10/2026 com site e ERP HTTP 200. Refs de branches públicas reescritas; clones WSL e Windows sincronizados e expurgados. PRD recebe artefato sem diretório .git e o HML compartilha o checkout WSL canônico. O GitHub ainda resolve um objeto órfão por SHA; expurgo hospedado pendente. Spec: docs/specs/p4-generalizar-referencias-publicas-infra.md.

- [x] [P3] CONCLUÍDO — Perfis de AliExpress e Alibaba ajustados às amostras; NF-e/DANFE enviada como Mercado Livre documentada como ambígua para manter seleção manual quando não há marca da plataforma. Testes de importação, compilação do backend e build de produção passaram; commit bd7f1f4 implantado em PRD em 09/10/2026 com smoke checks públicos HTTP 200. Spec: docs/specs/p3-reconhecimento-documentos-plataformas.md.

- [x] [P2] CONCLUÍDO — Notas de atualização em português com histórico retroativo linkado a 24 commits do GitHub, data de commit separada de deploy confirmado, acesso pelo README e regra para atualizar após novas implantações. Spec: docs/specs/p2-release-notes-github.md.

- [x] [P1] CONCLUÍDO — Campos monetários editáveis padronizados em BRL pt-BR, com validação de até duas casas decimais; fluxo QA padronizado documentado. Validado em HML; commit 6b90755 implantado em PRD e smoke checks públicos do site e ERP retornaram HTTP 200. Spec: docs/specs/p1-mascara-valores-moeda.md.

- [x] [P0] CONCLUÍDO — Recebimento parcial/total de materiais de despesas no almoxarifado, criação/vínculo de produtos, saldo e histórico auditável. Validado em HML; commit 747227f publicado e deploy/health checks públicos concluídos. Spec: docs/specs/p0-recebimento-estoque-compras.md.

- [x] CONCLUÍDO — Criar importação de compras por OCR, mantendo o cadastro manual; extrair do documento os dados do fornecedor, itens, quantidades, valores, datas e outros campos disponíveis, sempre para revisão antes de salvar. Validado visualmente em HML, dependências/modelos conferidos no ambiente de produção e publicado em PRD.

- [x] CONCLUÍDO — Adicionar a opção de manter a sessão ativa sem logout automático (“nunca deslogar”), com encerramento manual e revogação da sessão.

- [x] CONCLUÍDO — Implementar alertas push de segurança e disponibilidade pelo Firebase: tentativas de login e acessos negados anormais, mudanças de usuários/permissões e arquivos críticos, queda/reinício de serviços, fila parada e recursos esgotando. Usar gravidade, deduplicação e intervalo entre alertas; incluir monitor externo para detectar queda total do aparelho/internet. Solicitado em 07/10/2026, após a auditoria de segurança das APIs e do código.

- [x] CONCLUÍDO — Backups automáticos para o Google Drive: política de frequência e retenção de até 30 dias, autorização segura da conta Google, execução agendada no servidor, remoção automática das cópias vencidas e teste de restauração. Solução mantida sem credenciais nem tokens versionados.

## Fila solicitada — 07/10/2026

- [x] [P0] CANCELADO — Preparar um APK de teste para Apple iPhone (iOS), definindo o fluxo de distribuição e os requisitos de assinatura da Apple.
- [x] [P1] CONCLUÍDO — Usar em todos os objetos sincronizados do Mercado Livre e Shopee os timestamps fornecidos pelas plataformas, sem substituir por horário local do ERP.
- [x] [P2] CONCLUÍDO — Confirmar se os webhooks chegam e são processados imediatamente, medindo recebimento, fila, processamento e atualização no banco.
- [x] [P3] CONCLUÍDO — Documentar como funciona o horário de atualização do rastreio exibido no pedido, visão geral, faturas e pedidos do Mercado Livre.

- [x] [P5] CONCLUÍDO — Melhorar a esteira de status de venda em todos os objetos e telas, separando pedido, pagamento, fiscal, etiqueta, expedição e entrega. Status sugeridos: Pedido recebido → Pagamento aprovado → Aguardando NF → NF emitida → Aguardando etiqueta → Etiqueta disponível → Pronto para envio → Despachado → Em trânsito → Saiu para entrega → Entregue → Finalizado, com ramificações para pagamento pendente, revisão, cancelado, devolvido e falha na entrega.
