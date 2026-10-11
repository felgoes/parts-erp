# P7 — Simplificar pedido de compra e permitir exclusão segura

**Status:** fase 1 concluída em 10/10/2026, entregue em duas partes validadas em HML local e implantadas em PRD com smoke checks públicos do site e ERP em HTTP 200. Parte A (commit 6527b74): exclusão de rascunho com auditoria imutável, cancelamento com motivo e escolha explícita no recebimento parcial, encerramento de saldo, "receber tudo", título a pagar mínimo com baixa e estorno e rótulos de etapa unificados. Parte B (commit bbb6fe9): edição de cabeçalho e linhas do rascunho, inclusão e remoção de peças com SKU opcional no rascunho (exigido antes do pedido), cadastro leve de fornecedor com prazo padrão no próprio fluxo, número do pedido e data do documento em campos próprios, desconto por linha, valor total e paginação na lista, exclusão de rascunhos em lote e alerta de previsão vencida. Datas de calendário passaram a ser exibidas sem deslocamento de fuso. Suíte do backend com 97 testes e frontend com 22 testes verdes. Fase 2 (P8) registrada em "Faseamento".
**Prioridade:** P7

## Contexto e referências de mercado

O pedido é simplificar a criação/gestão de pedidos de compra e oferecer uma forma de excluir, atualmente ausente. A documentação oficial de Odoo, SAP Business One e Microsoft Dynamics 365 mostra padrões recorrentes: informar fornecedor e dados principais, adicionar produtos ou serviços em linhas, revisar quantidades e totais e confirmar/aprovar. Recebimento e fatura podem ser etapas relacionadas, mas distintas do pedido.

- [Odoo — fluxo padrão de compras e recebimento](https://www.odoo.com/documentation/saas-15.1/applications/finance/accounting/payables/supplier_bills/manage.html): cotação, confirmação em pedido, recebimento e fatura vinculada.
- [Microsoft Dynamics 365 — criar pedido de compra](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/purchase-order-creation): cabeçalho, linhas do pedido e revisão de totais.
- [Microsoft Dynamics 365 — aprovação, confirmação e cancelamento](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/purchase-order-approval-confirmation): pedidos confirmados não são simplesmente apagados; quantidades restantes podem ser canceladas conforme o que já foi recebido ou faturado.
- [SAP Business One — processo de compras](https://help.sap.com/docs/SAP_BUSINESS_ONE/68a2e87fb29941b5bf959a184d9c6727/450a572b37ca1f2ce10000000a1553f6.html): pedido, recebimento e fatura têm etapas e efeitos próprios.

As referências orientam usabilidade e integridade, sem exigir a cópia de módulos ou processos avançados que o Parts ERP não possui.

## Objetivo

Reduzir passos e campos não essenciais para registrar um pedido de compra, facilitar a inclusão e conferência dos itens e permitir excluir pedidos sem efeitos posteriores. Para pedidos que já tenham efeitos financeiros ou de estoque, oferecer cancelamento/estorno compatível com o estado do documento em vez de apagá-los silenciosamente.

## Diretrizes para a simplificação

- Priorizar um fluxo curto com fornecedor, dados essenciais do pedido e itens em uma tela/formulário coerente.
- Permitir adicionar, editar e remover linhas de itens sem perder os dados já digitados.
- Mostrar quantidade, valor unitário, descontos/frete quando aplicável e total de forma legível; recalcular totais após alterações.
- Usar dados padrão do fornecedor/produto quando disponíveis e manter campos opcionais fora do caminho principal.
- Validar dados essenciais com mensagens junto ao campo, preservando o preenchimento quando houver erro.
- Preservar o comportamento atual dos tipos de compra, produtos, recebimento de estoque e lançamentos financeiros. A simplificação não deve misturar etapas com efeitos diferentes.
- Mapear o fluxo atual antes de escolher o layout final e registrar os passos/campos simplificados, sem remover dados obrigatórios de negócio.

## Exclusão, cancelamento e integridade

- Permitir exclusão definitiva de pedidos em rascunho/estado inicial quando ainda não houver recebimento, lançamento financeiro, pagamento ou outro documento dependente.
- Pedir confirmação explícita, identificando pedido e fornecedor antes da exclusão definitiva.
- Se o pedido confirmado tiver recebimento, estoque, fatura, despesa, pagamento ou vínculo dependente, impedir apagamento físico simples. Oferecer cancelamento/estorno ou bloquear com explicação e orientação para resolver dependências.
- O cancelamento não pode apagar histórico nem deixar saldo, contas a pagar ou totais inconsistentes. Reverter efeitos por movimentos compensatórios rastreáveis, conforme as regras existentes do ERP.
- Registrar autor, data e motivo quando o cancelamento/estorno exigir auditoria.
- Duplo clique, repetição ou reenvio não pode excluir/cancelar duas vezes nem duplicar estornos.
- Manter distinção entre excluído, cancelado e concluído quando houver registro de auditoria.

## Critérios de aceite

1. O fluxo de criação apresenta claramente fornecedor, itens e total; a avaliação compara passos e campos antes/depois.
2. É possível adicionar, editar e remover itens antes de salvar sem perder os outros dados do pedido.
3. Itens e totais persistem corretamente e mantêm os vínculos de produto existentes.
4. Um rascunho sem efeitos relacionados pode ser excluído com confirmação e deixa de aparecer como pedido ativo.
5. Pedido com efeitos de estoque ou financeiros não pode ser apagado de modo a perder rastreabilidade ou deixar efeitos órfãos; há cancelamento/estorno seguro ou explicação do bloqueio.
6. Cancelamentos/estornos preservam histórico, autor e horário e não duplicam efeitos em caso de repetição.
7. Importação de compras, recebimentos e compra manual continuam funcionando; P3 e P6 mantêm escopo próprio.
8. A interface permanece utilizável em telas móveis e desktop.

## Dependências e verificações no início da implementação

- Inspecionar telas e APIs atuais de pedido/compra, tipos, estados e campos; medir os passos reais antes de simplificar.
- Mapear relações com itens, produtos, estoque, despesas/contas a pagar, pagamentos, recebimentos e importações.
- Identificar estados que permitem exclusão definitiva e estados que exigem cancelamento ou bloqueio.
- Reutilizar componentes de itens e vínculo/criação de produto existentes, sem tornar P7 dependente da implementação de P6.
- Preparar a proposta visual com base no formulário atual durante a implementação.

## Varredura do módulo atual (HML local, 10/10/2026)

Levantamento feito com API e frontend locais em execução, conta de QA dedicada e dados de teste. Referências de código: `frontend/src/app/pages/purchases/purchases.ts`, `backend/app/api/routes/purchases.py`, `backend/app/models/entities.py` (`PurchaseCase`, `PurchaseItem`, `PurchaseQuote`, `PurchaseEvent`, `PurchaseAttachment`) e `backend/app/schemas/common.py`.

### Como funciona hoje

- Uma única entidade (`purchase_cases`) cobre dois tipos: `parts` (peças para estoque) e `expense` (despesa da empresa, com `expense_category` e `expense_amount`).
- Estados em `status`: `negotiating` → `approved` → `ordered` → `partially_received` → `received`, além de `cancelled`. Despesa nasce direto em `ordered` (com materiais) ou `received` (sem materiais).
- Cotação por fornecedor (`purchase_quotes`) com custo unitário por item, frete, impostos, desconto, método de rateio, prazo e condição de pagamento; frete/impostos/desconto da cotação são rateados por item e compõem o custo final.
- Recebimento parcial ou total por item, com chave de idempotência e movimentação de estoque (`move_stock`).
- Auditoria por eventos (`purchase_events`), anexos (até 10 arquivos, 100 MB por compra) e importação por documento/OCR.
- Telas: lista com cards de resumo, filtro de período (padrão 30 dias), busca, filtro de etapa e tabela; modal de nova compra; modal de detalhe com etapas, itens/recebimento, cotações, documentos, resumo, histórico e "Cancelar compra"; menu de três pontos com "Copiar".

### O que já está bom

- Separação explícita entre negociação, pedido e recebimento, com estoque alterado apenas no recebimento.
- Custo por item com rateio de acréscimos/desconto e custo final recalculado.
- Recebimento idempotente e histórico com autor e data.
- Duplicação de compra ("Copiar") já disponível a partir da lista.

### Lacunas verificadas

1. **Não existe exclusão.** Não há rota `DELETE` em `purchases.py` nem ação na interface; a única saída é `POST /{id}/cancel`.
2. **Despesa lançada por engano é irrecuperável pela interface.** Despesa sem materiais nasce `received`, e o cancelamento é bloqueado para `received`/`cancelled`; o botão "Cancelar compra" também não aparece nesse estado. A correção só seria possível ajustando o banco.
3. **Cancelar compra parcialmente recebida não estorna estoque.** O endpoint muda o status e não gera movimento compensatório, deixando saldo creditado sem documento ativo.
4. **Não há como encerrar saldo pendente.** Sem receber tudo, a única saída é cancelar a compra inteira.
5. **Cabeçalho e linhas não são editáveis após a criação.** A API aceita apenas custos e quantidade (`PurchaseItemUpdate`) e a interface expõe somente custos; fornecedor, previsão, observações, descrição, SKU e unidade ficam travados.
6. **SKU é obrigatório para cadastrar peça manualmente**, mesmo com "Cadastrar/vincular depois" selecionado (validação no cliente e no servidor).
7. **Fornecedor é texto livre.** Não há cadastro de fornecedores, histórico por fornecedor, prazo ou condição de pagamento padrão.
8. **Dados do documento importado são achatados em texto.** Número do pedido, data do documento, frete, desconto, impostos e total identificados pelo OCR são gravados dentro de `notes`, em vez de campos próprios.
9. **Sem vínculo financeiro.** "Despesa" é apenas categoria + valor: não existe título a pagar, vencimento nem baixa. A spec cita contas a pagar, mas o ERP não tem esse módulo.
10. **Aprovação sem alçada.** Escolher uma cotação apenas muda o status, sem etapa de aprovação por perfil ou valor.
11. **Lista limitada.** Sem coluna de valor total para compras de peças, sem paginação (limite de 500 no servidor) e com período padrão de 30 dias, que esconde histórico.
12. **Rótulos divergentes.** Badge "Lançada" para despesa recebida contra a opção "Recebida" no filtro; o card "Aguardando recebimento" agrega `ordered` e `partially_received`.
13. **Recebimento item a item.** Não existe "receber tudo".
14. **Sem alerta de previsão.** `needed_by` não gera lembrete nem aviso de atraso.

## Referências de mercado e o que adotar

| Prática consolidada | Referência | Decisão para o Parts ERP |
| --- | --- | --- |
| Excluir somente documento em rascunho; documento confirmado é cancelado, não apagado | Odoo (RFQ em rascunho), Dynamics 365 (cancelar quantidades restantes), SAP Business One (cancelamento gera documento de reversão) | Adotar: exclusão definitiva restrita a rascunho sem efeitos |
| Cancelamento preserva histórico com motivo, autor e data | Dynamics 365, SAP Business One, NetSuite | Adotar: motivo obrigatório + evento de auditoria |
| Encerrar saldo não recebido sem cancelar o pedido | NetSuite (Close Order), Dynamics 365 (cancel remaining quantity) | Adotar: ação "encerrar saldo pendente" |
| Reverter efeitos por movimento compensatório, não por alteração destrutiva | SAP Business One, Odoo (reversão de movimentos) | Adotar: estorno de estoque rastreável |
| Fornecedor como registro mestre com prazo e condição padrão | Odoo (vendor), SAP (business partner) | Adotar de forma mínima (cadastro leve) ou autocomplete — decisão pendente |
| Linhas em grade com preço, desconto e imposto por item | Odoo, SAP, Dynamics 365 | Adotar: desconto percentual por linha além do rateio atual |
| Fluxo guiado com etapa no topo e resumo fixo de totais | Salesforce (Path e resumo fixo) | Evoluir o stepper existente e manter totais visíveis |
| Validação junto ao campo, sem perder o preenchimento | Salesforce, Odoo | Adotar |
| Título a pagar originado do pedido/recebimento | Odoo (vendor bill), NetSuite (Vendor Bill), SAP (AP Invoice) | Adotar título a pagar mínimo na fase 1; módulo completo na fase 2 |
| Duplicar documento a partir do registro | Odoo/SAP ("Copy from") | Já existe ("Copiar"); manter |
| Ações em lote na lista | Odoo, Salesforce | Adotar apenas para documentos elegíveis |
| Alçada de aprovação por valor | Dynamics 365, SAP | Não entra agora; reavaliar quando houver mais de um comprador |

## Mudanças propostas

### A. Ciclo de vida e integridade

- Tratar o estado inicial como rascunho/negociação e permitir exclusão definitiva apenas ali, quando não houver recebimento, movimentação de estoque, vínculo financeiro nem cotação aprovada.
- Introduzir "encerrar saldo pendente" para concluir uma compra sem receber o restante, com registro de auditoria.
- Permitir cancelamento em `negotiating`, `approved` e `ordered`. Com recebimento parcial, exigir escolha explícita: manter o recebido e encerrar o saldo, ou registrar devolução ao fornecedor com saída documentada antes de cancelar.
- Bloquear exclusão/cancelamento destrutivo quando existirem efeitos, oferecendo estorno rastreável em vez de apagamento.
- Corrigir a lacuna da despesa lançada por engano: editar com trilha ou excluir/cancelar com estorno, sempre pela interface.

### B. Permissões

- Manter exclusão e cancelamento restritos a `purchases:manage` (admin/manager); operador segue com leitura e recebimento.
- Registrar autor, data e motivo obrigatório em cancelamento, estorno e exclusão.

### C. Edição e campos

- Em rascunho/negociação, permitir editar cabeçalho (fornecedor, previsão, observações) e linhas (descrição, SKU, unidade, quantidade), inclusive remover linhas sem efeitos.
- Após o pedido, manter a edição restrita a custos e a quantidades ainda não recebidas.
- Permitir peça sem SKU no rascunho, exigindo SKU ou produto vinculado antes do pedido/recebimento.
- Persistir em campos próprios o número do pedido do fornecedor e a data do documento identificados na importação, em vez de texto em `notes`.

### D. Interface

- Lista: exibir valor total das compras de peças, permitir paginação, preservar filtros e habilitar ações em lote somente nos registros elegíveis.
- Detalhe: adicionar "Receber tudo", reabrir edição do rascunho e expor as ações "Excluir rascunho", "Cancelar compra" e "Encerrar saldo" com motivo.
- Unificar os rótulos de estado entre cards, filtro, badges e histórico.
- Manter o formulário enxuto: dados essenciais do pedido em primeiro plano, opcionais fora do caminho principal, validação junto ao campo.

### E. Auditoria e acompanhamento

- Registrar eventos para exclusão, cancelamento, estorno e encerramento de saldo.
- Alertar sobre previsão vencida (`needed_by`) na lista e no detalhe.

### F. Financeiro (fase 1)

- Despesa lançada e compra recebida geram um título a pagar com fornecedor, valor, vencimento, vínculo ao documento de origem e status aberto/pago.
- Cancelamento encerra o título com estorno, sem apagar o registro financeiro.
- Baixa do título disponível no detalhe da compra/despesa nesta fase; a visão consolidada de contas a pagar fica na fase 2.

## Decisões tomadas (10/10/2026)

Decisões fechadas com base na varredura acima e nos padrões de Odoo, Dynamics 365, SAP Business One, NetSuite e Salesforce. Nenhum ponto fica em aberto para iniciar a implementação.

1. **Exclusão definitiva restrita a rascunho sem efeitos.** A compra só pode ser apagada enquanto não houver cotação escolhida, pedido enviado, recebimento, movimentação de estoque ou vínculo financeiro. Fora disso, o caminho é cancelar ou encerrar o saldo. Documento com efeito não se apaga: apagar destrói rastreabilidade, impede auditoria e abre espaço para perda e fraude. A numeração pode ficar com lacunas, prática normal em ERP, e toda exclusão gera registro de auditoria imutável com número, fornecedor, itens, autor e data.
2. **Cancelamento com recebimento parcial mantém o que chegou.** Estoque recebido é fato físico e não se estorna automaticamente. O cancelamento passa a exigir escolha explícita: encerrar o saldo pendente mantendo o recebido regularizado, ou registrar devolução ao fornecedor com saída de estoque documentada e só então cancelar. Sem isso, o sistema fica com saldo creditado por documento cancelado, como acontece hoje.
3. **Permissões: admin e manager excluem e cancelam; operator lê e recebe.** Sem alçada por valor nesta fase. A operação é de loja única com poucos usuários e a alçada adicionaria burocracia sem cadeia de aprovação. Motivo obrigatório e auditoria cobrem o controle; a alçada volta à pauta quando houver mais de um comprador.
4. **Fornecedor com cadastro leve, criado no próprio fluxo.** Nome obrigatório, contato, prazo de entrega padrão e condição de pagamento padrão, com CNPJ opcional nesta fase. A criação acontece inline no próprio campo, no padrão Odoo, sem etapa extra. É o que habilita histórico por fornecedor, reaproveitamento de prazo e condição e a recompra a partir de "Copiar".
5. **Título a pagar entra no ciclo com escopo mínimo.** Despesa lançada e compra recebida geram título a pagar com fornecedor, valor, vencimento, vínculo ao documento e status aberto/pago; o cancelamento encerra o título em vez de apagá-lo. Fica na fase 1 porque as regras de cancelamento e estorno desta spec não se sustentam sobre um passivo que não existe. Visão consolidada, pagamentos parciais, aging e conciliação ficam na fase 2.
6. **Despesa lançada por engano: editar enquanto não houver baixa financeira; excluir ou cancelar com estorno depois.** Antes de qualquer pagamento, correção de valor, categoria e fornecedor com trilha de auditoria. Com pagamento ou conciliação registrados, apenas cancelamento com estorno do título. É a separação entre corrigir erro de digitação e preservar o efeito contábil.

## Faseamento

- **Fase 1 (esta spec).** Ciclo de vida com exclusão de rascunho, cancelamento e encerramento de saldo; edição de cabeçalho e linhas em rascunho; cadastro leve de fornecedor; número do pedido e data do documento em campos próprios; desconto por linha; "receber tudo"; título a pagar mínimo criado e encerrado pela compra; auditoria e rótulos consistentes.
- **Fase 2 (P8).** Contas a pagar como módulo: visão consolidada, baixa com pagamentos parciais, aging, conciliação e relatórios. Escopo herdado da decisão 5, entregue em 10/10/2026 no commit 2e5a0f7 e documentado em `docs/specs/p8-contas-a-pagar-modulo.md`.

## Fora de escopo

- Portal de fornecedor, cotação online, envio automático de pedido por e-mail ou EDI.
- Múltiplas moedas e detalhamento fiscal brasileiro (ICMS/IPI/ST) ou emissão de documento fiscal.
- Contratos, catálogo de fornecedor e cotações de terceiros.
- Migração ou reescrita em lote de compras já existentes.

## Critérios de aceite adicionais (varredura de 10/10/2026)

9. Rascunho sem efeitos pode ser excluído definitivamente com confirmação e registro de auditoria.
10. Despesa lançada por engano tem caminho de correção pela interface, sem ajuste manual no banco.
11. Cancelar compra com recebimento parcial não deixa estoque creditado sem documento ativo: o recebido é mantido com o saldo encerrado, ou sai por devolução documentada antes do cancelamento.
12. É possível encerrar saldo pendente sem receber o restante, mantendo o histórico.
13. Peça pode ser criada sem SKU no rascunho, com identificação exigida antes do pedido/recebimento.
14. Número do pedido do fornecedor e data do documento importados ficam em campos próprios, consultáveis e filtráveis.
15. A lista mostra o valor total das compras de peças e habilita ações em lote apenas nos registros elegíveis.
16. Rótulos de estado são consistentes entre cards, filtro, badges e histórico.
17. Exclusão de rascunho gera registro de auditoria imutável com número, fornecedor, itens, autor e data.
18. Cancelamento com recebimento parcial exige escolha explícita entre encerrar o saldo mantendo o recebido ou registrar devolução com saída de estoque documentada.
19. Despesa lançada e compra recebida geram título a pagar com fornecedor, valor, vencimento e status, e o cancelamento encerra o título sem apagá-lo.
