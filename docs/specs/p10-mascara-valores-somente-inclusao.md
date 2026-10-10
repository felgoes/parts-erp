# P10 — Máscara de valores forte, somente inclusão

**Status:** proposta — aguardando decisões do PO antes da implementação
**Prioridade:** P2

## Objetivo

Fazer o campo de valor em reais ser impossível de quebrar. O texto exibido está sempre no formato completo `R$ 0,00` com separador de milhar, e a única coisa que o usuário consegue fazer é acrescentar dígitos. Apagar remove o último dígito digitado; a vírgula, o ponto de milhar e o `R$` nunca saem do lugar.

## História do usuário

Como operador do ERP, quero digitar valores sem risco de deixar o campo num estado esquisito, para nunca salvar `1.234,`, `,56` ou algo parecido e para não perder tempo corrigindo máscara.

## Comportamento da máscara

- **Formato sempre completo:** o campo exibe `R$ 1.234,56`, com vírgula decimal e ponto de milhar. Em repouso e durante a digitação o formato nunca fica parcial.
- **Somente inclusão:** cada dígito digitado entra no fim e empurra o valor. `1` → `R$ 0,01`; `12` → `R$ 0,12`; `1234` → `R$ 12,34`; `1234567` → `R$ 12.345,67`.
- **Apagar remove só o último dígito:** backspace/delete tira o último dígito do valor e o campo continua formatado. `R$ 12,34` → `R$ 1,23` → `R$ 0,12` → `R$ 0,01` → `R$ 0,00`.
- **Separadores são intocáveis:** não é possível apagar, digitar, selecionar e trocar a vírgula, o ponto de milhar, o `R$` nem os zeros dos centavos. Tentar isso não muda nada e o cursor volta para o fim.
- **Caracteres não numéricos são ignorados:** letras, sinais, `%` e símbolos não entram no campo.
- **Colar continua aceito:** colar `R$ 1.234,56`, `1234,56`, `1234.56` ou `1.234,56` grava exatamente 1234 reais e 56 centavos; o texto colado é reduzido aos dígitos e interpretado como centavos.
- **Foco e seleção:** ao focar, o valor fica selecionado para ser substituído por digitação nova, mantendo o formato visível; sem modo de edição de texto livre.
- **Sem estado inválido por máscara:** como não existe entrada parcial nem terceira casa decimal, o erro "máximo de duas casas" deixa de ser alcançável pela digitação. Valores legados com mais de duas casas continuam sinalizados ao abrir o campo.
- **Campo somente leitura:** continua apenas exibindo o valor formatado, sem capturar teclado.
- **Substitui:** esta regra substitui, na P1, a edição livre de texto durante o foco e os critérios que exigiam editar e apagar trechos no meio do valor.

## Referência de mercado (ERP)

- **Padrão brasileiro:** Bling, Omie, Conta Azul, retaguardas fiscais e aplicativos bancários usam digitação por centavos, com o valor crescendo da direita para a esquerda e separadores fixos. É o comportamento pedido aqui.
- **SAP Fiori:** usa digitação livre com separador decimal e validação ao confirmar. É um caminho diferente e mais permissivo; fica registrado como desvio consciente do padrão escolhido.
- **Acessibilidade:** os ERPs de mercado mantêm colagem, navegação por teclado e leitores de tela com a máscara aplicada; a máscara forte não pode quebrar isso.
- **Eficiência de digitação:** quem lança nota de fornecedor, contas a pagar e preço de catálogo digita dezenas de valores por dia. Máscara previsível é ganho direto de produtividade, e é por isso que o padrão por centavos venceu no mercado brasileiro.

## Impacto administrativo

- **Precisão do dado:** o valor é persistido em centavos inteiros e a máscara nunca cria estado parcial, então nenhum lançamento financeiro nasce de um número ambíguo.
- **Conferência:** os erros mais comuns de digitação de valor no Brasil são `1.234,` e `,56`. A máscara forte elimina a categoria inteira.
- **Colagem da nota:** copiar valor do XML, do PDF da nota ou de e-mail do fornecedor é rotina no fechamento; bloquear colagem seria inaceitável na operação.
- **Risco a evitar:** campo opcional vazio virando zero silencioso em frete e desconto distorce custo de aquisição e título a pagar. Vazio e zero precisam ser decisões distintas.

## Pontos que precisam de decisão do PO

1. **Campo opcional vazio:** o campo vazio mostra `R$ 0,00` fixo ou fica realmente em branco até o primeiro dígito? (Afeta frete, desconto, impostos e outros campos opcionais.)
2. **Campo obrigatório com valor zero:** `R$ 0,00` é aceito como valor preenchido quando o mínimo do campo é maior que zero, ou continua bloqueando o salvamento com a mensagem atual?
3. **Corrigir o meio do número:** não será possível, por desenho, apagar só um dígito do meio. A correção passa a ser reescrever o valor. Confirmar que essa é a intenção.

**Recomendação (ERP e administração):** 1) campo opcional fica em branco até o primeiro dígito, porque zero e vazio significam coisas diferentes em frete e desconto; campo obrigatório com mínimo maior que zero continua bloqueando o salvamento; 2) confirmar a correção por reescrita — é o comportamento do padrão por centavos e evita estado parcial.

## Fora de escopo

- Quantidades, percentuais, pesos, dimensões e valores não monetários.
- Moeda estrangeira e sinal negativo (mantém o comportamento atual de cada campo).
- Apresentação de valores somente leitura e relatórios, que já usam formato pt-BR.

## Critérios de aceite

1. Digitar `1234` mostra `R$ 12,34` e grava 12,34; a cada dígito novo o campo permanece formatado.
2. Apagar repetidamente passa por `R$ 1,23`, `R$ 0,12`, `R$ 0,01` e `R$ 0,00`, sem nunca mostrar vírgula solta, campo vazio por acidente nem ponto de milhar errado.
3. Tentar apagar ou substituir a vírgula, o ponto de milhar ou o `R$` não altera o valor nem o formato.
4. Colar `R$ 1.234,56` grava exatamente 1234,56, e colar texto com letras ignora os caracteres inválidos.
5. Não é possível produzir pela digitação um valor com três casas decimais.
6. O valor enviado à API representa centavos exatos e as validações de mínimo e máximo continuam valendo.
7. A regra vale em todos os campos monetários editáveis do ERP, e campos somente leitura não mudam.
8. Teclado numérico abre corretamente no celular e a digitação funciona igual em desktop e mobile.
