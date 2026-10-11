# P12 — Condição de pagamento da cotação gera as parcelas do título a pagar

**Status:** concluída — decisões do PO fechadas em 10/10/2026 e implementadas
**Prioridade:** P4

## Objetivo

Transformar a condição de pagamento negociada com o fornecedor em parcelas reais do título a pagar. Hoje a condição da cotação é texto livre ("30/60 dias") e o título nasce sem vencimentos, obrigando a redigitar no contas a pagar e abrindo espaço para vencimento errado.

## História do usuário

Como responsável financeiro, quero que o prazo que combinei com o fornecedor vire as parcelas do título a pagar, para não lançar de novo e para saber exatamente o que vence em cada data.

## Referência de mercado (ERP)

- **SAP:** condições de pagamento com datas base e percentuais de parcela; o vencimento é derivado da condição, não digitado à mão.
- **TOTVS Protheus:** condições de pagamento cadastradas (à vista, 30, 30/60, 30/60/90) que geram as parcelas do título na aprovação, com prazo em dias corridos.
- **Omie, Bling e Conta Azul:** a compra/despesa carrega a condição de pagamento e o financeiro nasce parcelado, com o total dividido igualmente.
- **Conclusão do benchmark:** condição de pagamento é dado estruturado e reutilizável, e as parcelas são derivadas dela. Texto livre não fecha o ciclo financeiro.

## Impacto administrativo e financeiro

- **Fluxo de caixa:** sem parcelas com vencimento, o contas a pagar não alimenta previsão de caixa nem alerta de vencido — que é o principal motivo de existir o módulo.
- **Conferência com o fornecedor:** o boleto/duplicata chega com vencimentos; o ERP precisa ter os mesmos vencimentos antes, para conferir em vez de apenas registrar.
- **Auditoria:** condição, data base e parcelas ficam rastreáveis; alteração depois de pagamento é controlada.
- **Operação enxuta:** a condição é escolhida uma vez na cotação e reaproveitada, sem digitação duplicada no financeiro.

## Escopo

- **Cotação:** substituir o campo de texto livre "Condição de pagamento" por condição estruturada: tipo (à vista, parcelado, entrada + parcelas), quantidade de parcelas, prazo do primeiro vencimento em dias, intervalo entre parcelas em dias e um campo opcional de observação livre. Atalhos prontos: à vista, 30 dias, 30/60, 30/60/90, além de configuração livre.
- **Geração do título:** na aprovação da compra com cotação escolhida, o título a pagar nasce já parcelado conforme a condição. Compra sem cotação escolhida não gera título (regra da P9).
- **Despesa da empresa:** aceita a mesma condição estruturada, opcional. Sem condição informada, o título nasce com um único vencimento na data do documento.
- **Parcelas:** cada parcela tem número, vencimento (data, sem hora) e valor. A baixa continua por parcela, e a baixa parcial dentro da parcela mantém o comportamento atual do contas a pagar.
- **Alteração de condição:** depois de o título existir, mudar a condição recalcula apenas as parcelas ainda não baixadas, com registro de auditoria. Parcela já paga não é alterada.
- **Rastreabilidade:** o título guarda a condição legível usada (por exemplo `30/60/90`) para conferência, além das parcelas individuais.

## Regras

- Prazos em dias corridos, prática comercial brasileira; não usar dias úteis.
- A soma das parcelas é exatamente o valor do título; a diferença de centavos do rateio fica na última parcela.
- Data base do primeiro vencimento: data do documento da compra quando informada; caso contrário, a data da aprovação.
- Não permitir parcela com valor menor ou igual a zero nem intervalo de zero dia entre parcelas de um parcelamento.
- Entrada + parcelas é calculada sobre o total líquido; a entrada vence na data base e as demais seguem o intervalo informado.
- Vencimentos são datas sem hora; a exibição segue o fuso `America/Sao_Paulo`, conforme a regra do projeto.

## Decisões fechadas

1. **Prazos em dias corridos**, com atalhos prontos e configuração livre.
2. **Data base é a data do documento da compra** e, quando ela não existir, a data da aprovação.
3. **Parcelas iguais, com a sobra de centavos na última**, exatamente como no rateio da cotação.
4. **Condição é estruturada e o texto livre vira observação opcional**, sem servir como fonte de cálculo.
5. **Parcela paga não se altera**; mudança de condição afeta apenas o saldo em aberto e fica auditada.
6. **Despesa sem condição informada gera vencimento único na data do documento**, mantendo o comportamento atual simples.

## Fora de escopo

- Boletos, remessa e retorno bancários, conciliação bancária e integração de pagamento.
- Juros, multa, correção e desconto financeiro por antecipação.
- Recorrência automática de despesas e contratos com reajuste.
- Alterar o cálculo do custo de aquisição e o rateio da cotação, tratados na P11.

## Critérios de aceite

1. Ao registrar uma cotação com condição `30/60`, a compra aprovada gera título com duas parcelas de vencimentos correspondentes e soma exatamente igual ao total.
2. Condição `30/60/90` de uma despesa de R$ 100,00 gera três parcelas de 33,33, 33,33 e 33,34.
3. Compra sem cotação escolhida continua sem título, e nenhuma parcela é criada.
4. Despesa sem condição informada gera um único vencimento na data do documento.
5. Não é possível salvar condição com valor de parcela zero, negativa ou intervalo de zero dia entre parcelas.
6. Título mostra a condição usada e as parcelas individuais com vencimento e valor.
7. Baixa por parcela funciona e a baixa parcial mantém o comportamento atual.
8. Alterar a condição com parcelas já pagas recalcula somente o que está em aberto e registra a mudança.
9. Vencimentos aparecem como data, sem deslocamento de um dia, em desktop e mobile.

## Verificação

- No HML local: criar compra de peças, registrar cotações com condições diferentes, escolher vencedora, aprovar e conferir o título parcelado.
- Testar valor quebrado em centavos e conferir o fechamento na última parcela.
- Testar despesa sem condição, condição com entrada e alteração de condição com uma parcela já baixada.
