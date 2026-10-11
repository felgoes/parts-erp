# P6 — Vincular itens importados aos produtos do estoque

**Status:** concluído; implantado em PRD em 10/10/2026 (commit `0ec83fe`); site e ERP HTTP 200. Validação manual em HML dispensada por solicitação do usuário.  
**Prioridade:** P6

## Contexto

A importação de arquivo reconhece dados da compra, mas as linhas de item não ficam necessariamente vinculadas a produtos cadastrados no estoque. A revisão da importação precisa oferecer o mesmo vínculo e a mesma criação de produto disponíveis no lançamento manual de compra.

Esta tarefa complementa a P3: a P3 trata do reconhecimento dos campos do documento; esta tarefa trata de relacionar cada linha reconhecida ao catálogo de produtos e salvar a compra com esses vínculos.

## Objetivo

Ao revisar uma compra importada, permitir que o usuário selecione o produto de estoque correspondente a cada item ou cadastre um produto novo quando não houver correspondência. Salvar os itens como linhas reais da compra, vinculadas aos produtos selecionados/criados, sem exigir recadastro manual da compra inteira.

## Fluxo esperado

1. Importar o documento e preencher os campos reconhecidos, incluindo as linhas de itens.
2. Para cada linha, mostrar descrição extraída e um campo específico de **Produto do estoque**.
3. Permitir buscar e selecionar produto existente por nome, SKU ou código de barras, exibindo informação suficiente para distinguir produtos parecidos.
4. Se o produto não existir, permitir iniciar o cadastro pelo mesmo formulário/validação de criação usado no lançamento manual de compra; ao concluir, vincular o novo cadastro à linha atual.
5. Preservar na linha da compra os valores próprios do documento (descrição, quantidade, preço, desconto e total), mesmo que o nome cadastrado do produto seja diferente.
6. Revisar os vínculos antes de salvar e criar a compra e seus itens no mesmo fluxo de confirmação existente.

## Regras de negócio

- Não selecionar ou criar produto silenciosamente com base apenas em semelhança textual. Correspondência ambígua exige escolha explícita do usuário.
- Produto novo só é criado após ação explícita e preenchimento dos campos obrigatórios do cadastro padrão; não inventar SKU, código de barras ou atributos ausentes.
- A criação do produto deve ser atômica com o fluxo da compra ou recuperável sem gerar item duplicado se a gravação da compra falhar.
- Para linhas de bens controlados pelo estoque, exigir produto selecionado/criado antes de confirmar a compra. Uma linha identificada pelo usuário como serviço ou item sem controle de estoque pode permanecer sem produto, se o modelo de compra permitir esse tipo de linha.
- Os dados extraídos continuam editáveis e sujeitos à confirmação humana. A importação nunca confirma que a mercadoria foi recebida.
- Criar a compra importada não pode, por si só, duplicar entrada de estoque ou lançamento financeiro. A movimentação de estoque segue o fluxo de recebimento aplicável à modalidade da compra, incluindo o comportamento definido na P0 para materiais de despesa.
- Respeitar os tipos de compra, categorias, validações e vínculos do fluxo manual já existente; não criar um segundo modelo de compra paralelo para importações.

## Fora de escopo

- Melhorar OCR, layouts ou perfis de plataforma (P3).
- Recebimento físico, saldo, entrada parcial e histórico de almoxarifado além dos fluxos já definidos (P0 e fluxo existente de peças para estoque).
- Correspondência automática por IA sem confirmação explícita.
- Alterar o cadastro mestre de produtos ou os campos obrigatórios fora do necessário para reutilizar o cadastro padrão.

## Critérios de aceite

1. Cada item reconhecido aparece na revisão da importação com descrição e campo específico para associar produto do estoque.
2. O usuário consegue localizar e selecionar produto existente, e o item salvo referencia esse produto.
3. Quando não houver produto, o usuário consegue criá-lo pelo cadastro padrão e retornar à importação com o novo produto vinculado.
4. Produtos parecidos ou correspondência incerta não são vinculados automaticamente sem escolha do usuário.
5. Itens da compra importada são persistidos como os itens da compra manual, mantendo quantidades e valores revisados.
6. Serviços/linhas não controladas pelo estoque seguem as regras atuais e não exigem produto artificialmente.
7. Falha ou repetição da confirmação não deixa produto, item, compra, lançamento financeiro ou movimentação duplicados.
8. Salvar a importação não marca os itens como recebidos nem duplica movimentos de estoque; recebimento continua rastreável pelo fluxo apropriado.
9. A confirmação humana da compra permanece obrigatória.

## Dependências e verificações no início da implementação

- Mapear o formulário manual de compra, cadastro/seleção de produto, tipos de compra e payload de itens para reutilizar os mesmos componentes e regras.
- Verificar como a importação atual representa linhas sem SKU, linhas de serviço e produtos não encontrados.
- Definir tratamento de erro/transação para criação do produto seguida da falha ao salvar a compra.
- Confirmar em quais modalidades o produto é obrigatório e como as linhas sem controle de estoque são representadas no modelo atual.
- Executar verificações de regressão do fluxo manual, da importação e dos recebimentos vinculados (P0).
