# Ambiente local reproduzível (WSL Ubuntu)

Use WSL Ubuntu e mantenha o checkout do app em `~/workspace/garagista/parts-erp-main`. O repositório do app é privado (clone e pull exigem credencial). O checkout privado de infraestrutura é configurado localmente em cada máquina; não publique seu nome ou caminho.

Não use pasta sincronizada por OneDrive/Dropbox para checkouts, bancos ou backups. Não copie `.env`, bancos, backups, chaves SSH ou tokens entre máquinas.

## Versões e instalação

Use nvm no WSL e Python 3.12. Os pins estão em `.nvmrc` e `.python-version`:

```bash
nvm install
nvm use
npm install --global npm@11.19.0
cd ~/workspace/garagista/parts-erp-main
./scripts/setup-local.sh
```

O script valida as versões, cria `backend/.venv`, instala dependências Python e executa `npm ci` pelo lockfile. Execute em cada PC. Não cria nem preenche segredos.

## HML local em um comando

Suba API, ERP e login de QA no WSL a partir do checkout canônico:

```bash
./scripts/hml-local.sh start     # sobe tudo e mostra os endereços
./scripts/hml-local.sh status    # mostra o que está ativo e as portas
./scripts/hml-local.sh logs      # acompanha os logs dos três serviços
./scripts/hml-local.sh stop      # encerra só o que o script iniciou
```

O script confere os pré-requisitos, cria `backend/.env` a partir de `.env.qa.local` quando ele ainda não existe, aplica as migrações do banco de QA, sobe backend (`127.0.0.1:8000`), frontend (`127.0.0.1:4200`) e o helper de login (`127.0.0.1:8765`), e só libera quando os três respondem. Serviços já ativos em outra sessão são adotados em vez de reiniciados, e `stop` encerra apenas os processos iniciados pelo próprio script. Para usar outras portas, defina `PARTS_ERP_API_PORT` e `PARTS_ERP_WEB_PORT`.

Também é possível subir cada serviço manualmente com `cd frontend && npm start`. Mantenha valores reais em `backend/.env`, ignorado pelo Git. Use credenciais locais independentes, nunca credenciais de produção. Para validar login e fluxos de UI no HML local, o Codex usa o perfil de QA definido localmente em `.env.qa.local` (ignorado pelo Git) e preenche o formulário de login por conta própria. Não compartilhe esses dados em chat, logs ou capturas de tela; nunca use uma conta de produção para QA.

## Atalhos da esteira

```bash
./scripts/dev/checks.sh backend test_purchase_import    # só o que casar (nome ou arquivo), para iterar rápido
./scripts/dev/checks.sh frontend src/app/shared/purchase-import-math.spec.ts
./scripts/dev/checks.sh all                             # portão antes do push: backend + frontend + build
./scripts/dev/sync.sh start | finish | status           # alternância entre as duas máquinas (veja docs/duas-maquinas.md)
./backend/.venv/bin/python scripts/dev/import_smoke.py  # smoke do fluxo de importação de compra no HML local
./scripts/dev/secret-scan.sh                            # varredura de segredo antes do push (o finish já roda)
```

O `setup-local.sh` só roda `npm ci` quando o `package-lock.json` mudou (use `--force-deps` para
forçar). Para um único spec durante a implementação, `cd frontend && npx ng test --watch` mantém
o runner aquecido e reexecuta o que mudou.

Documento de amostra para revisar a importação pelo navegador:
`scripts/dev/fixtures/nfe-amostra-pecas.xml` (sintético, sem dados reais).

## Deploy em produção

Siga as instruções disponíveis no checkout privado de infraestrutura configurado localmente para verificar a conexão e executar o wrapper oficial de deploy. Ao concluir uma mudança funcional do app, faça build e checks, commit e push antes do deploy. Confirme os health checks locais e externos do site e do ERP. Se conexão, deploy ou health check falhar, informe o bloqueio e não declare a entrega concluída. A configuração de conexão e as chaves ficam fora dos repositórios, em diretórios locais com permissões restritas.

## Verificação antes de compartilhar

```bash
git status --short
git check-ignore backend/.env
git check-ignore .env.qa.local
```

Os dois últimos comandos devem confirmar que os arquivos são ignorados. Se um segredo foi publicado, revogue-o no serviço emissor: apagar um arquivo não limpa o histórico Git.
