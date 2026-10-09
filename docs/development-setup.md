# Ambiente local reproduzível (WSL Ubuntu)

[historical infra reference removed]

[historical infra reference removed]
[historical infra reference removed]

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

Inicie o frontend com `cd frontend && npm start`. Mantenha valores reais em `backend/.env`, ignorado pelo Git. Use credenciais locais independentes, nunca credenciais de produção.

[historical infra reference removed]

Siga `goesautoparts-infra/docs/s9-setup.md` para criar uma chave SSH individual, preencher configuração privada local, validar a conexão e fazer deploy. Configuração e chave ficam em `~/.config/parts-erp/` e `~/.ssh/`, nunca nos repositórios.

## Verificação antes de compartilhar

```bash
git status --short
git check-ignore backend/.env
git check-ignore .env.qa.local
```

Os dois últimos comandos devem confirmar que os arquivos são ignorados. Se um segredo foi publicado, revogue-o no serviço emissor: apagar um arquivo não limpa o histórico Git.
