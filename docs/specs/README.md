# Especificações — Parts ERP

As specs descrevem comportamento e critérios de aceite de cada item. A lista oficial do que está pendente é o `TASKS.md` do projeto.

## Abertas

1. [P5 — Taxa extra na compra de importação](p5-taxa-extra-compra-importacao.md)

## Histórico

- [P31 — Configurações organizadas, IA compartilhada e Carros no Brasil](settings-ai-vehicle-market.md) — entregue em produção em 24/10/2026 (`f0d0d66`).
- [P29/P30 — Cadastro da empresa e estudos orientados a mercado](company-profile-market-studies-v2.md) — entregue em produção em 24/10/2026 (`ac18ed9`).
- [P28 — Endereço de destino e histórico de rastreio legível](p28-endereco-historico-rastreio.md) — entregue em produção em 24/10/2026 (`490e932`).
- [P27 — Estudos de mercado para autopeças](market-studies-autopecas.md) — entregue em produção em 23/10/2026 (`1c2e84e`).

Specs de tarefas concluídas são removidas a pedido do PO e permanecem no histórico do Git; o que foi entregue em produção fica registrado no `RELEASE_NOTES.md`.

- Removidas em 11/10/2026: P1, P2, P3, P4, P7, P8, P9 e P12.
- Removidas em 16/10/2026: P0, P6, P10, P11, P13, P14 e P15, todas entregues em produção.
- P16 — backup que avisa, guarda cópia local e sobrevive à queda do Drive — entregue em 16/10/2026 (`835d511`). A spec fica aqui como documentação do comportamento que existe.
- P17 — atualizar a tela no app (puxar para atualizar e retomar a atualização automática) — entregue em 16/10/2026 (`7e50cd4`), com a conferência em aparelho Android real ainda pendente.
- P14 — importação de documento de marketplace: as fases 1 e 2 estão entregues em produção (moeda e cotação, valor pago, duplicidade, conferência de fechamento, leitura de itens por coluna e por OCR, vínculo por SKU e tipo do lançamento). A **fase 3** — salvar os rótulos revisados como perfil da loja e analisar vários documentos em fila — foi descartada pelo PO em 16/10/2026; a importação segue com revisão e correção a cada documento.
