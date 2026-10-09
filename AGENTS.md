# Parts ERP project rules

## Datas e fusos horários

- Toda data/hora recebida de marketplace, webhook ou dispositivo deve ser interpretada com o fuso informado pela origem.
- Persistir timestamps de operação em UTC, sempre com timezone explícito; nunca criar ou serializar `datetime` ingênuo.
- Respostas da API devem marcar timestamps UTC com `Z` (ou `+00:00`).
- A interface deve exibir datas operacionais no fuso `America/Sao_Paulo` (UTC−03:00), usando o locale `pt-BR`.
- Ao revisar uma tela, notificação, relatório ou histórico com data, verificar os três pontos: origem, persistência e apresentação. Adicionar teste para conversão quando houver risco de deslocamento.

## Canonical development environment

- Use the WSL Ubuntu checkout as the canonical working copy. Make source changes, builds, Git commits, and GitHub pushes from WSL; do not develop in the Windows mirror.
- Keep separate parts-erp checkouts and branches intact.
- Never commit `.env.qa.local`, passwords, private keys, Cloudflare tokens, Firebase keys, or other secrets.

## Required delivery order

- For application changes, build and run relevant checks locally, review the changed flow, commit and push the exact commit, then, when deployment is requested, use the private infrastructure wrapper `deploy/update-s9-template.sh` (it invokes `deploy/update-s9.sh`) and verify the production health endpoint.
- Do not deploy a commit that differs from `origin/main`. Preserve production data and configuration.

## Project commands

- Frontend production build: `cd frontend && npm ci && npm run build -- --configuration production`
- Backend syntax check: `cd backend && python -m compileall -q app`
[historical infra reference removed]

## Production server connection

[historical infra reference removed]
- Never add internal addresses, SSH users, passwords, private-key paths, tokens, or connection commands with concrete values to tracked files.
- Use the private project configuration to run a read-only batch-mode SSH connectivity check before deploy, then use the official deploy script.
- If the connection is unavailable, report the blocker and request the current private project configuration; do not guess hosts or copy values into the repository.

## Shared period filters

- Use `frontend/src/app/shared/period-filter.ts` for date-range filtering in dashboard, invoices, monitoring, and future pages.
- Keep the shared component responsive and review desktop and mobile layouts when its markup or styles change.

## Android APK releases

- Keep APK signing keys and `frontend/android/app/google-services.json` out of Git and off the public server.
- A new APK must preserve the signing key to update an existing installation.
## Shared project steering

- This file is the shared operating standard for the Parts ERP across the public app repository and private infrastructure repository. The private repository may add infrastructure-specific rules, but must not contradict these shared security and development rules.
[historical infra reference removed]
[historical infra reference removed]
[historical infra reference removed]
[historical infra reference removed]
- Before changing public files, inspect the diff and scan newly added content for secrets. A secret accidentally committed must be revoked at its issuer; deleting it from the latest revision does not remove it from Git history.
