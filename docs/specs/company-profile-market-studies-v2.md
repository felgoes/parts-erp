# P30/P29 — Cadastro da empresa e estudos orientados a mercado

**Status:** entregue em produção em 24/10/2026. Commit:
`ac18ed96da8f9af0ed4c870ad436025c3b9a9372`. Site e ERP verificados com
HTTP 200 após o deploy.

## P30 — Cadastro fiscal e operacional

Configurações possui um perfil empresarial único, com revisão otimista,
histórico imutável e completude por finalidade:

- identificação, atividades, endereço fiscal/comercial e contato;
- regime tributário, ICMS e vigência;
- margem-alvo, comissão, tarifa, frete e devoluções;
- habilitação de importação, Incoterm, modal, desembaraço e spread cambial.

Somente administradores leem e alteram o perfil completo. A API de estudos
recebe apenas os parâmetros operacionais necessários e registra o identificador
da versão usada.

O Cartão CNPJ em PDF, JPG ou PNG é validado e processado localmente, com limite
de 10 MB, cinco páginas para PDF e 30 megapixels para imagem. PDF usa primeiro
a camada textual; imagem ou PDF digitalizado usa OCR em português. A resposta
contém apenas campos permitidos, confiança, origem, lacunas e diferenças. QSA,
CPF e nomes de sócios não são retornados nem armazenados. A aplicação e a
gravação são ações separadas; apenas hash, tipo, leitura e data ficam no perfil.

A consulta cadastral oficial permanece explicitamente indisponível enquanto o
Serpro/Conecta não estiver contratado. O Cartão CNPJ e o preenchimento manual
continuam disponíveis. Situação não ativa exige confirmação explícita.

## P29 — Estudo de mercado

O fluxo parte de uma única seleção, marca ou nacionalidade. A outra dimensão é
derivada no backend pelo mapa editorial versionado. A esteira cruza catálogo,
aplicações, concorrência, economia e riscos, sem transformar hipótese em fato.

As rotas são páginas completas:

- `/market-studies`: biblioteca paginada, filtros, retorno preservado e aba
  Carros no Brasil;
- `/market-studies/new`: seleção e premissas revisáveis;
- `/market-studies/:id`: decisão, candidatos, evidências, limitações, memória
  de cálculo e ações.

A lista retorna apenas resumos. Estudos salvos são imutáveis e guardam o
snapshot das premissas da empresa. Valores ausentes aparecem como não
informados; não viram zero. Sem custo de compra, cotação real ou base fiscal por
NCM, a decisão máxima continua em negociação ou validação.

Emplacamentos e frota registrada têm armazenamentos, definições e exibições
separados. A importação é idempotente por fonte, tipo e competência, rejeita
duplicidades e variações anômalas e preserva a última publicação válida.
Enquanto não houver publicação validada, a tela informa a indisponibilidade em
vez de estimar totais.

Execuções com consulta externa são assíncronas e a página acompanha o estado.
O cache e o snapshot evitam nova cobrança automática em caso de falha.

## Fornecedores na China

A flag de sourcing está implementada e desligada por padrão. Sem API licenciada
do Alibaba e sem regras fiscais configuradas, o resultado informa que nenhuma
empresa ou cotação foi pesquisada. O adaptador de fixture só pode ser ativado
fora de produção e, sem registros, também retorna indisponibilidade explícita.
Nenhum fornecedor, preço, MOQ, prazo ou alíquota é inventado.

## Verificação

- 268 testes de backend e 83 testes de frontend aprovados.
- Build de produção aprovado e gate estrutural sem arquivos novos acima de
  400 linhas.
- HML validado em desktop e viewport móvel de 390 × 844.
- Massa QA identificável removida e serviços locais encerrados.
