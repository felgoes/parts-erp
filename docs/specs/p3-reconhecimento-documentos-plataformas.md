# P3 — Perfis de reconhecimento de documentos por plataforma

**Status:** concluída para as amostras recebidas.
**Prioridade:** P3

## Objetivo

Melhorar os perfis declarativos de importação de compras para reconhecer campos e itens de recibos das plataformas com base nas amostras fornecidas, mantendo a revisão humana antes de criar qualquer compra.

## Escopo

- Perfis nativos já existentes; ajustes nesta tarefa limitados aos leiautes fornecidos: AliExpress, Alibaba e uma NF-e/DANFE associada pelo usuário a uma compra do Mercado Livre.
- Identificação segura da plataforma e extração de fornecedor, número/data do pedido, subtotal, frete, descontos, impostos, total e linhas de itens disponíveis nas amostras.
- Compatibilidade com documentos em imagem e PDF processados pelo OCR existente; NF-e XML mantém seu parser dedicado.
- Fixtures textuais sintéticas e anonimizadas, baseadas nos rótulos/leiautes das amostras, para testar variações reais sem versionar documentos originais, dados pessoais ou detalhes de pedidos.
- Perfil desconhecido, baixa confiança e campos ambíguos continuam visíveis para revisão manual; nunca escolher valores sem evidência.

## Critérios de aceite

1. Cada amostra fornecida tem sua plataforma identificada ou explicitamente marcada como ambígua. A DANFE associada pelo usuário ao Mercado Livre não contém marca legível da plataforma; não se deve inferi-la pelo nome do destinatário ou transportadora.
2. Os campos e linhas suportados são extraídos com valores corretos nos casos de teste derivados das amostras.
3. Variações de rótulos e leiaute ficam declaradas nos perfis versionados, sem código executável enviado pelo perfil.
4. Documentos sem amostra ou sem evidência suficiente preservam o comportamento conservador e exigem conferência.
5. Os documentos originais, informações pessoais, chaves de pedido e dados de compra não são incluídos no Git.
6. Build e testes relevantes passam; a importação manual e a revisão continuam funcionais.

## Progresso

- AliExpress: reconhece ID/data do pedido, subtotal, descontos, frete, impostos e total em rótulos do leiaute recebido; aceita datas como `28 set, 2026`, moeda `BRL` e item com descrição/variante/preço/quantidade em linhas separadas.
- Alibaba: reconhece vendedor, número/data do recibo, subtotal, frete e `Order total`; não usa `Payment total` como total do pedido e não converte automaticamente valores entre BRL e USD.
- Mercado Livre: a amostra é NF-e/DANFE. O parser existente de NF-e XML permanece; este PDF sem marca textual continua sem perfil automático para evitar classificar somente pelo vendedor, destinatário ou transportadora.
- A amostra de DANFE continua ambígua quanto à plataforma no próprio documento; exige seleção manual. Perfis sem leiaute analisado mantêm as regras genéricas existentes e revisão manual.
