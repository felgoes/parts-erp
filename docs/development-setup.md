# Ambiente local reproduzível (WSL Ubuntu)

Use WSL Ubuntu e mantenha o checkout público do app em `~/workspace/garagista/parts-erp-main`. O checkout privado de infraestrutura é configurado localmente em cada máquina; não publique seu nome ou caminho.

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

Inicie o frontend com `cd frontend && npm start`. Mantenha valores reais em `backend/.env`, ignorado pelo Git. Use credenciais locais independentes, nunca credenciais de produção. Para validar login e fluxos de UI no HML local, o Codex usa o perfil de QA definido localmente em `.env.qa.local` (ignorado pelo Git) e preenche o formulário de login por conta própria. Não compartilhe esses dados em chat, logs ou capturas de tela; nunca use uma conta de produção para QA.

## Deploy em produção

Siga as instruções disponíveis no checkout privado de infraestrutura configurado localmente para verificar a conexão e executar o wrapper oficial de deploy. Ao concluir uma mudança funcional do app, faça build e checks, commit e push antes do deploy. Confirme os health checks locais e externos do site e do ERP. Se conexão, deploy ou health check falhar, informe o bloqueio e não declare a entrega concluída. A configuração de conexão e as chaves ficam fora dos repositórios, em diretórios locais com permissões restritas.

## Verificação antes de compartilhar

```bash
git status --short
git check-ignore backend/.env
git check-ignore .env.qa.local
```

Os dois últimos comandos devem confirmar que os arquivos são ignorados. Se um segredo foi publicado, revogue-o no serviço emissor: apagar um arquivo não limpa o histórico Git.
