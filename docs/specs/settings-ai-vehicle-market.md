# P31 — Configurações organizadas, IA compartilhada e Carros no Brasil

**Status:** entregue em produção em 24/10/2026. Commit:
`f0d0d66`; a pesquisa completa de marcas foi complementada em `c8423a7`.
Site e ERP verificados com HTTP 200 após cada deploy.

## Configurações

A página Geral deixou de concentrar todos os formulários. Configurações agora
possui navegação por finalidade e rotas próprias:

- visão geral;
- identidade;
- empresa;
- fiscal;
- parâmetros de estudo;
- importação;
- documentos;
- aparência;
- backups;
- inteligência artificial.

Cada rota renderiza somente a seção correspondente. A visão geral oferece
acesso direto às páginas menores.

## Inteligência artificial compartilhada

O conector de IA dos estudos reutiliza a configuração compartilhada já usada
pelo assistente do ERP. Provedor, modelo, orçamento e chave criptografada são
os mesmos; nenhuma segunda credencial é necessária.

O estudo por marca ou nacionalidade envia somente evidências determinísticas e
solicita explicação no schema `market_opportunity_result.v1`. A resposta é
validada, só pode citar candidatos existentes e não altera score, decisão,
preço, custo ou alíquota. Falha de IA preserva o resultado determinístico.

## Carros no Brasil

A página foi separada da biblioteca de estudos e adicionada ao menu Análise.
Ela mantém um único escopo de período e permite filtrar nacionalidade, marca e
categoria.

### Emplacamentos

Fonte: FENABRAVE por meio da API pública gratuita FIPE API BRASIL.

- Top 20 por segmento, com atualização parcial da competência corrente.
- Cache de seis horas no backend para preservar a cota.
- Cota pública de 5 consultas por dia sem chave; chave gratuita opcional
  permite até 300 consultas por mês.
- A chave, quando usada, permanece no backend e pode vir do ambiente.
- Marca e nacionalidade são derivadas por mapa editorial.
- Modelos desconhecidos aparecem como “Não mapeado/Não informada” e permanecem
  no total, sem descarte silencioso.
- O seletor usa o catálogo completo de marcas, mesmo quando a marca está fora
  do Top 20.
- Ao selecionar uma marca fora do ranking, a tela lista suas famílias e versões
  no catálogo FIPE e informa que não há volume publicado para ela naquela
  competência.
- YTD é a soma das competências já coletadas pelo ERP; a tela não preenche
  meses ausentes.

### Frota registrada

Fonte: conjunto oficial RENAVAM no Portal de Dados dos Transportes, atualização
mensal em arquivo ZIP/RAR.

A API CKAN é usada para identificar a publicação mais recente e oferecer o link
oficial. Totais e rankings de frota só aparecem após importação do arquivo; a
tela não estima valores ausentes. A publicação oficial identificada durante a
entrega era setembro/2026.

## Verificação

- 274 testes de backend e 83 testes de frontend aprovados após a pesquisa
  completa de marcas.
- Build de produção e gate estrutural aprovados.
- HML desktop e viewport de 390 × 844 validados.
- Snapshot automotivo da massa QA removido e serviços locais encerrados.
