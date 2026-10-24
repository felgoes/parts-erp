# Spec funcional — Estudos de mercado para autopeças

Status: Entregue em produção em 23/10/2026. Commit: `1c2e84e4607e60e9c91752c1ecb1d8e8e5b9d56c`. Site e ERP verificados com HTTP 200, incluindo os bundles JavaScript.

## 1. Objetivo

Ajudar a decidir se vale a pena **comprar ou anunciar uma autopeça**, combinando anúncios comparáveis no Mercado Livre com custo, estoque e vendas da loja no ERP.

O estudo fornece sinais para uma decisão humana. **Não prevê vendas garantidas, não compra produtos e não altera anúncios automaticamente.**

## 2. Escopo

A entrega deve:

- simplificar a criação de um estudo;
- preencher automaticamente dados já disponíveis no ERP;
- melhorar a identificação e a comparação de autopeças compatíveis;
- mostrar preços e cálculos de margem com suas premissas;
- manter os estudos consultáveis;
- permitir iniciar um rascunho de negociação de compra.

Ficam fora da primeira entrega: compra automática, alteração automática de preços, promessa de demanda futura e integração com outros marketplaces.

## 3. Usuários e permissões

- **Gerente ou administrador:** pode gerar estudos e iniciar uma negociação de compra.
- **Demais usuários autorizados ao módulo:** podem consultar estudos salvos.
- Os dados e estudos devem respeitar as regras de acesso da empresa/conta no ERP.

## 4. Fluxo principal

### Etapa 1 — Identificar a peça

Mostrar um campo principal:

**“Qual peça você quer analisar?”**

Aceitar SKU/código interno, código OEM, código de barras ou descrição.

Exibir os resultados encontrados no ERP para seleção. Se houver mais de uma correspondência, pedir que a pessoa escolha a peça correta.

### Etapa 2 — Confirmar a aplicação

Após selecionar uma peça cadastrada, mostrar um resumo para conferência:

- descrição e marca;
- SKU e código OEM, se disponíveis;
- aplicação: marca, modelo, ano, motor e versão;
- lado ou posição, quando aplicável.

A pessoa confirma que selecionou a peça certa.

Se a peça não estiver cadastrada, permitir continuar com:

- descrição ou código OEM;
- aplicação do veículo, quando conhecida;
- custo de compra, somente se quiser calcular margem e esse dado não estiver disponível.

### Etapa 3 — Gerar o estudo

Botão principal: **“Analisar mercado”**.

O ERP busca e preenche automaticamente os dados disponíveis:

- custo da peça;
- frete de entrada rateado;
- estoque atual;
- vendas internas dos últimos 90 dias;
- taxas padrão do canal configuradas pela empresa.

Só deve solicitar dados que estiverem faltando. A ausência de custo não deve impedir a pesquisa de preços; nesse caso, informar que a margem não pôde ser calculada.

## 5. Campos

### Tela principal

Exigir apenas:

- identificação e seleção da peça — ou descrição/código se ela não estiver cadastrada;
- confirmação da aplicação, quando houver dados disponíveis.

### Preenchidos pelo ERP

- SKU e descrição;
- custo unitário;
- frete de entrada rateado;
- estoque;
- vendas internas recentes;
- taxa padrão do canal.

### “Mais opções”

Manter recolhidos inicialmente:

- editar custo de compra;
- editar frete de entrada;
- taxa do canal;
- frete de saída pago pelo vendedor;
- margem desejada;
- categoria ou termo adicional para busca.

A interface deve indicar quais valores vieram do ERP, quais são padrões e quais foram editados pela pessoa.

## 6. Pesquisa e comparação de anúncios

- Consultar até 50 anúncios ativos do Mercado Livre, conforme os limites e regras da integração.
- Mostrar os anúncios usados na comparação, com título, preço, link e dados de aplicação disponíveis.
- Remover duplicados e anúncios claramente incompatíveis antes dos cálculos.
- Priorizar, em ordem, código OEM exato, produto de catálogo correspondente e compatibilidade por atributos do veículo.
- Usar semelhança de descrição como evidência fraca, não como confirmação de compatibilidade.
- Se a aplicação não puder ser confirmada, identificar o anúncio como **“compatibilidade não confirmada”** e não misturá-lo silenciosamente com correspondências fortes.

### Confiança da comparação

Classificar a amostra:

- **Alta:** OEM correspondente ou compatibilidade confirmada, com dados suficientes.
- **Média:** atributos compatíveis, mas sem confirmação completa.
- **Baixa:** comparação baseada principalmente em descrição ou termo genérico.

Exibir quantidade e qualidade da amostra, por exemplo:

> 18 anúncios comparáveis de 50 encontrados · Confiança média

Como valor inicial, sinalizar amostra pequena quando houver menos de 5 anúncios comparáveis. Não exibir uma recomendação conclusiva nesses casos. O limiar deve poder ser ajustado pela equipe do produto.

## 7. Resultados

No início do resultado, mostrar uma conclusão curta:

- **Oportunidade para investigar**
- **Margem apertada ao preço de mercado**
- **Preço de mercado abaixo do custo**
- **Poucos anúncios comparáveis**
- **Dados insuficientes para estimar margem**

A conclusão deve ser acompanhada por uma explicação curta e pelos dados que a sustentam. Não usar linguagem que prometa vendas ou resultados futuros.

### Indicadores de mercado

- preço mediano dos anúncios comparáveis;
- menor e maior preço observado;
- quantidade de anúncios considerados;
- data e hora da consulta;
- nível de confiança da amostra;
- links para conferir os anúncios.

Não usar o menor preço sozinho como recomendação: os anúncios podem ter condições diferentes ou não representar a mesma peça.

### Indicadores da loja

Quando houver SKU:

- unidades vendidas nos últimos 90 dias;
- média mensal observada — vendas de 90 dias divididas por três;
- estoque atual;
- cobertura aproximada do estoque, apenas se houver vendas recentes.

Identificar a média como **observada, não prevista**. Sem histórico suficiente, mostrar “Sem histórico suficiente”.

### Tendências

Mostrar termos relacionados separadamente dos dados de vendas. Tendências indicam interesse de busca, não garantia de compra. A API do Mercado Livre descreve a atualização semanal desse recurso. [Documentação de tendências do Mercado Livre](https://developers.mercadolivre.com.br/pt_br/relatorios-de-faturamento/tendencias).

## 8. Cálculos financeiros

Os resultados devem identificar os custos e taxas usados. A taxa de marketplace pode variar por categoria e condições da venda; mostrar a taxa aplicada no estudo.

### Custo posto na loja

`custo posto = custo de compra + frete de entrada rateado + outros custos de entrada cadastrados`

### Margem estimada no preço mediano

`margem estimada (%) = (preço mediano − custo posto − comissão percentual − tarifa fixa − frete de saída − outros custos variáveis) ÷ preço mediano × 100`

Incluir apenas componentes conhecidos e informar quais entraram no cálculo. Não tratar componentes desconhecidos como zero sem aviso.

### Preço necessário para a margem desejada

Quando as taxas e os custos aplicáveis estiverem disponíveis:

`preço-alvo = (custo posto + tarifa fixa + frete de saída + outros custos fixos) ÷ (1 − comissão percentual − margem desejada)`

Se a taxa e a margem desejada tornarem o cálculo inválido, explicar o motivo e não mostrar um preço-alvo enganoso.

A quantidade disponível em anúncios públicos pode ser aproximada, conforme a documentação do Mercado Livre. Não apresentar disponibilidade de concorrentes como estoque confirmado. [Documentação de busca de itens](https://developers.mercadolivre.com.br/pt_br/itens-e-buscas).

## 9. Ações

Após revisar o resultado, oferecer:

- **Criar negociação de compra:** abre um rascunho em Compras para incluir fornecedores e cotações. Não cria pedido automaticamente.
- **Revisar anúncio:** leva à tela ou aos anúncios correspondentes para avaliação manual.
- **Ver anúncios comparáveis:** abre a lista dos anúncios utilizados.
- **Salvar e consultar depois:** mantém o estudo na biblioteca de análises.

Não alterar preços nem fazer pedidos sem ação explícita da pessoa usuária.

## 10. Integrações e IA

### Mercado Livre

A integração com o Mercado Livre deve ser configurada no ambiente administrativo do ERP; não deve ser um campo obrigatório no formulário de cada estudo.

Se estiver indisponível, mostrar uma mensagem clara de que a pesquisa não pôde ser concluída e preservar os dados preenchidos para uma nova tentativa.

### IA

A IA é opcional:

- sem IA, pesquisa, indicadores e cálculos devem funcionar;
- com IA, gerar uma síntese qualitativa sem substituir ou contradizer os indicadores;
- não enviar dados de clientes ou pedidos;
- informar que o provedor escolhido pode cobrar pelo uso.

## 11. Estados e mensagens

A tela deve prever:

- carregamento: **“Analisando mercado…”**;
- integração indisponível;
- nenhum anúncio encontrado;
- poucos anúncios comparáveis;
- compatibilidade não confirmada;
- custo ou outros dados financeiros ausentes;
- SKU não localizado;
- falha temporária ou limite de consultas;
- estudo concluído e salvo.

Em caso de erro, preservar o que a pessoa preencheu.

## 12. Critérios de aceite funcional

1. Gerente ou administrador consegue buscar uma peça por SKU, OEM ou descrição.
2. Ao selecionar um SKU cadastrado, o ERP preenche custo, estoque e histórico disponíveis.
3. É possível gerar um estudo sem configurar IA.
4. Com a integração ativa, o resultado mostra anúncios, quantidade de comparáveis e data da consulta.
5. Correspondências incertas ficam identificadas; não são apresentadas como compatibilidade confirmada.
6. A margem mostra a fórmula, taxas e custos usados.
7. Tendências e vendas acumuladas de anúncios concorrentes não são apresentadas como previsão mensal.
8. Com dados insuficientes, o resultado mostra a limitação e evita uma recomendação forte.
9. Criar negociação gera apenas um rascunho, sem pedido.
10. Estudos concluídos ficam salvos e respeitam as permissões.
11. Erros não apagam os dados preenchidos.
12. A tela inicial pede a identificação da peça; os campos avançados ficam em “Mais opções”.

## 13. Critérios de aceite visual e responsividade

Validar em larguras de **320, 360, 390, 768, 1024 e 1280 px**.

- Em celular, não pode haver rolagem horizontal da página, campos cortados, texto sobreposto ou botões inacessíveis.
- Em desktop, o conteúdo deve usar bem o espaço sem deixar campos ou linhas de texto excessivamente largos.
- Os rótulos devem deixar claro:
  - obrigatório ou opcional;
  - preenchido pelo ERP ou editável;
  - valor em reais ou percentual;
  - custo de entrada ou frete de saída.
- Termos como “custo posto na loja” e “margem estimada” devem ter uma explicação curta junto ao campo ou indicador.
- “Mais opções” deve estar recolhido inicialmente e não pode esconder dados necessários para concluir o estudo.
- No celular, os resultados devem reorganizar-se em blocos legíveis. Listas de anúncios podem virar cartões; tabelas podem ter rolagem limitada ao próprio componente.
- Botões, alertas, carregamento e erros devem permanecer legíveis e utilizáveis nas larguras testadas.
- Campos e ações devem funcionar com teclado, apresentar foco visível e explicar como corrigir erros.
- Revisar visualmente os estados de busca, “Mais opções” aberto, carregamento, resultado completo, amostra pequena e erro de integração em celular, tablet e desktop.
- Testes automatizados não substituem a conferência visual nesses tamanhos.

## 14. Plano mínimo de testes

Testar:

- SKU com custo, estoque e vendas;
- SKU sem vendas recentes;
- peça não cadastrada, com OEM e aplicação;
- pesquisa sem custo;
- taxa e margem padrão e ajustadas manualmente;
- zero resultados e amostra menor que o mínimo;
- anúncios compatíveis e com compatibilidade não confirmada;
- integração indisponível e limite de consultas;
- usuário sem permissão para gerar estudo;
- IA desligada e ligada;
- criação de rascunho sem gerar pedido;
- cálculos com comissão percentual e tarifa fixa;
- preservação dos campos depois de falha;
- critérios visuais e responsividade da seção 13.

## 15. Prioridade de implementação

**MVP:** simplificar o formulário, preencher dados do ERP, sinalizar a compatibilidade e qualidade da amostra, tornar os cálculos transparentes, manter histórico e permitir rascunho de negociação.

**Depois do MVP:** avaliar outras fontes de mercado, melhorias de comparação de catálogo e ferramentas de análise adicionais. Previsão de demanda não faz parte desta entrega.

Status: Em implementação (iniciado em 23/10/2026).
