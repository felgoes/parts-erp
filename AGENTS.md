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

- For application changes, build and run relevant checks locally, review the changed flow, commit and push the exact commit, then deploy with `deploy/update-s9.sh` and verify the production health endpoint.
- Do not deploy a commit that differs from `origin/main`. Preserve production data and configuration.

## Project commands

- Frontend production build: `cd frontend && npm ci && npm run build -- --configuration production`
- Backend syntax check: `cd backend && python -m compileall -q app`
- Deploy only through `deploy/update-s9.sh`; it runs migrations, restarts Termux services, and checks health.

## Production server connection

- Production is the Android/Termux server on SSH port `8022`, application directory `/data/data/com.termux/files/home/parts-erp`.
- Use the configured SSH key/alias; never put credentials in Git.
- Health check: `curl -fsS http://127.0.0.1:8080/health` over SSH.

## Shared period filters

- Use `frontend/src/app/shared/period-filter.ts` for date-range filtering in dashboard, invoices, monitoring, and future pages.
- Keep the shared component responsive and review desktop and mobile layouts when its markup or styles change.

## Android APK releases

- Keep APK signing keys and `frontend/android/app/google-services.json` out of Git and off the public server.
- A new APK must preserve the signing key to update an existing installation.
