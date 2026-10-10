# P4 — Generalizar referências públicas à infraestrutura

**Status:** concluída
**Prioridade:** P4

## Objetivo

Remover do conteúdo atual do repositório público referências identificáveis ao repositório privado de infraestrutura e a uma máquina/instância específica de produção. Manter instruções compartilhadas que sejam úteis em qualquer ambiente e preservar o contrato usado pelo fluxo oficial de deploy.

## Escopo

- Revisar arquivos rastreados de instrução e operação: `AGENTS.md`, `README.md`, `TASKS.md`, `docs/`, `deploy/` e configurações mantidas no repositório.
- Generalizar nomes/URLs do repositório privado, caminhos locais ou remotos, aliases de conexão, endereços, nomes de usuário, hostname, modelo/apelido do dispositivo e identificadores equivalentes que apontem para a infraestrutura individual do operador.
- Manter nomes de domínios públicos do produto, comandos públicos, nomes genéricos de serviços e requisitos operacionais que não revelem uma instância privada.
- Reescrever instruções usando termos genéricos como “checkout privado de infraestrutura”, “servidor de produção” e “wrapper oficial de deploy”, conforme o contexto.
- Revisar notas de auditoria versionadas para preservar descobertas e recomendações sem expor identificadores de uma máquina ou configuração privada.
- Preservar as regras de segurança e release compartilhadas em `AGENTS.md`, incluindo uso de WSL, localização canônica do app, leitura da configuração privada fora do Git, verificação SSH em modo batch e deploy pelo wrapper oficial.
- Manter, por compatibilidade, os nomes históricos das variáveis de ambiente e dos entrypoints executáveis usados pelo wrapper privado; generalizar as instruções e mensagens voltadas ao operador sem expor valores de conexão.

## Fora do escopo

- Alterar o conteúdo do repositório privado de infraestrutura ou a configuração operacional local.
- Mudar o comportamento, os argumentos, os nomes históricos das variáveis de ambiente ou os caminhos dos scripts de deploy chamados pelo wrapper privado; não renomear nem remover entrypoints usados pelo fluxo atual.
- Trocar domínios públicos do produto, credenciais, arquitetura ou configuração de produção.
- Reescrever o histórico Git público nesta tarefa. A implementação deve verificar se identificadores removidos do HEAD permanecem acessíveis em commits anteriores e registrar esse limite; qualquer limpeza de histórico requer um plano separado porque altera refs públicas e clones existentes.

## Critérios de aceite

1. A busca no conteúdo documental rastreado do HEAD não encontra o nome/slug confirmado do repositório privado nem o modelo, hostname, endereço ou outros identificadores da máquina/instância específica. Nomes históricos de scripts e variáveis mantidos estritamente como contrato de compatibilidade são exceção e não podem vir acompanhados de valores reais.
2. As instruções públicas continuam explicando, sem detalhes privados, como preparar o ambiente, obter a configuração local segura, verificar conectividade e chamar o fluxo oficial de deploy.
3. `AGENTS.md` permanece suficiente como fonte das regras compartilhadas; requisitos específicos de operação de produção ficam descritos em termos de função e configuração privada, sem depender do nome do checkout ou de dados específicos do servidor.
4. Os entrypoints, argumentos, caminhos e verificações invocados pelo wrapper oficial permanecem compatíveis; não há alteração de comportamento de deploy.
5. Domínios públicos, achados de segurança relevantes, instruções de proteção e requisitos de health check continuam corretos após a generalização.
6. Uma checagem automatizada ou documentada procura regressões dos identificadores confirmados nos documentos rastreados, sem imprimir valores sensíveis nos logs; ela distingue os nomes de interface de compatibilidade que precisam permanecer nos scripts.
7. O diff contém apenas conteúdo público generalizado e não introduz credenciais, endereços internos, nomes de usuário, chaves ou novos dados operacionais.

## Verificação

- Inventariar ocorrências nos arquivos rastreados, classificando cada uma como identificador privado, requisito genérico ou domínio público que deve ser mantido.
- Repetir as buscas após as alterações e revisar o diff completo; validar que o wrapper oficial ainda chama os mesmos entrypoints e argumentos.
- Executar os checks relevantes de documentação/configuração e o build aplicável. Não executar deploy apenas para provar que os arquivos de instrução foram generalizados; o deploy de uma mudança funcional posterior continua seguindo o fluxo padrão do projeto.


## Resultado da implementação

- Generalizadas as instruções compartilhadas em `AGENTS.md`, `README.md` e `docs/development-setup.md`; removida a referência ao nome/caminho do checkout privado.
- Generalizados os registros de validação OCR para omitir o modelo e os dados de capacidade do aparelho específico, preservando resultados e recomendações técnicos relevantes.
- Mensagens de erro do deploy agora descrevem a configuração ausente sem nomear servidor ou checkout privado. Os nomes legados de variáveis e entrypoints foram mantidos como contrato do wrapper.
- A varredura do conteúdo documental rastreado não encontrou identificadores da infraestrutura individual. Em uma solicitação posterior, o histórico foi reescrito em todas as refs locais (branches remotas, tags e stash), substituindo as linhas removidas por marcadores neutros; os clones locais serão sincronizados e objetos inacessíveis expurgados após a publicação. A árvore funcional implantada permanece idêntica.
- `bash -n deploy/update-s9.sh` e `git diff --check` passaram. O wrapper privado ainda exporta os mesmos nomes de variáveis e chama o mesmo entrypoint público; seu código e configuração não foram alterados.
- O commit `7e08f44` foi implantado em PRD em 09/10/2026; o Tunnel foi preservado e os smoke checks do site e do ERP retornaram HTTP 200.
