# P1 — Máscara e precisão para valores em reais

**Status:** concluído; validado em HML e implantado em PRD no commit , com smoke checks públicos do site e ERP em HTTP 200
**Prioridade:** P1

## Objetivo

Padronizar a digitação e a apresentação de todos os campos monetários do ERP em reais, com formato pt-BR e no máximo duas casas decimais.

## História do usuário

Como usuário do ERP, quero digitar, colar e corrigir valores em reais com uma máscara previsível, para que preços e totais não aceitem casas decimais excedentes nem sejam interpretados incorretamente.

## Comportamento da máscara

- Usar vírgula como separador decimal e ponto para milhares. Exemplos: `R$ 12,00`, `R$ 1.234,56`.
- Mostrar o prefixo `R$` e agrupar milhares em campos editáveis e valores apresentados.
- Aceitar entrada sem agrupamento (`1234,56`) e com agrupamento pt-BR (`1.234,56`). Aceitar valor inteiro (`1234`) e uma casa decimal (`1234,5`), completando visualmente os centavos ao sair do campo.
- Aceitar colagem de valores com `R$`, espaços e separadores brasileiros, normalizando para o valor correto.
- Interpretar ponto como separador de milhares quando estiver em grupos válidos de três dígitos. Não assumir que ponto é separador decimal; a entrada decimal usa vírgula.
- Manter edição previsível: digitar, inserir no meio, selecionar, apagar e substituir trechos não deve deslocar o cursor de forma inesperada nem bloquear correções.
- Em dispositivos móveis, abrir teclado decimal apropriado e continuar permitindo vírgula.
- Implementar um controle compartilhado de moeda, usado por todos os campos monetários editáveis, em vez de máscaras isoladas por tela.
- Valores somente para leitura continuam formatados, sem comportamento de campo editável.

## Precisão, validação e dados

- Permitir zero, uma ou duas casas decimais. Nunca aceitar uma terceira casa decimal como valor válido.
- Se a digitação ou colagem contiver mais de duas casas, preservar o texto para correção, sinalizar o campo e impedir o salvamento. Não truncar nem arredondar silenciosamente.
- Rejeitar combinações de separadores inválidas ou ambíguas com mensagem curta, sem transformar o valor em outro número.
- Campo opcional pode ficar vazio; obrigatoriedade e sinal negativo seguem as regras já existentes do campo.
- O valor numérico enviado à API deve representar centavos exatos. A máscara é somente apresentação e não participa dos cálculos.
- Subtotais e totais devem permanecer consistentes ao editar, salvar e reabrir. Não converter repetidamente texto formatado para ponto flutuante durante cálculos.
- Não alterar em lote dados históricos. Se um valor legado tiver mais de duas casas, a edição deve sinalizá-lo e pedir correção explícita antes de salvar.

## Cobertura global

A regra vale para **todos os campos de valores monetários presentes no ERP**, em qualquer tela ou fluxo, sem exceções por módulo. Isso inclui catálogo/produtos, compras e despesas, cotações, vendas/pedidos, faturas, pagamentos, financeiro, estudos de mercado, configurações, documentos importados e qualquer funcionalidade existente ou futura que aceite dinheiro em reais.

Inclui campos em formulários, modais, tabelas editáveis, filtros de valor, importação/revisão de documentos e edição rápida. Valores calculados ou somente para leitura também usam apresentação monetária pt-BR com duas casas, mas não recebem máscara de entrada.

A implementação deve inventariar o ERP inteiro e centralizar o controle de entrada e os formatadores monetários compartilhados. Nenhum campo monetário pode permanecer com entrada numérica livre que aceite precisão diferente da regra.

## Fora de escopo

- Quantidades, percentuais, peso, dimensões, câmbio e números de série.
- Alteração em lote ou migração automática de dados já salvos.
- Entrada de valores em moeda estrangeira.

## Critérios de aceite

1. `1234`, `1234,5` e `1234,56` são aceitos e apresentados como `R$ 1.234,00`, `R$ 1.234,50` e `R$ 1.234,56`.
2. Colar `R$ 1.234,56` grava exatamente 1234 reais e 56 centavos.
3. Entradas com terceira casa decimal não são salvas nem arredondadas; o campo informa que aceita no máximo duas casas.
4. Separadores inválidos não resultam em um valor diferente sem aviso.
5. Digitar, editar no meio, selecionar, apagar e colar funcionam com cursor previsível em desktop e dispositivo móvel.
6. Todos os campos monetários editáveis em todos os módulos e fluxos do ERP usam o comportamento compartilhado; nenhum permanece fora da máscara.
7. Campos de quantidade, percentual e outros valores não monetários mantêm a precisão e apresentação próprias.
8. Campo somente leitura, campo opcional vazio, validação de obrigatoriedade e restrição a valores negativos continuam respeitados.
9. Valores e cálculos permanecem iguais após salvar e reabrir.
10. Nenhum registro histórico é modificado sem ação explícita do usuário.

## Decisões para verificar durante a implementação

- Fazer inventário global de todos os campos de entrada e apresentação monetária do ERP, incluindo fluxos menos usados, para evitar lacunas.
- Definir uma mensagem de validação única para casas decimais excedentes e formato inválido.
- Confirmar comportamento de navegação por teclado e acessibilidade do prefixo e das mensagens.
