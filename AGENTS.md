# Parts ERP project rules

## Datas e fusos horários

- Toda data/hora recebida de marketplace, webhook ou dispositivo deve ser interpretada com o fuso informado pela origem.
- Persistir timestamps de operação em UTC, sempre com timezone explícito; nunca criar ou serializar `datetime` ingênuo.
- Respostas da API devem marcar timestamps UTC com `Z` (ou `+00:00`).
- A interface deve exibir datas operacionais no fuso `America/Sao_Paulo` (UTC−03:00), usando o locale `pt-BR`.
- Ao revisar uma tela, notificação, relatório ou histórico com data, verificar os três pontos: origem, persistência e apresentação. Adicionar teste para conversão quando houver risco de deslocamento.

## Canonical development environment

- Before running a WSL command, list installed distributions from Windows with wsl.exe --list --quiet and pass the exact installed name to wsl.exe -d. Do not assume the distro is named Ubuntu; on the current PC it is Ubuntu-24.04. If WSL reports WSL_E_DISTRO_NOT_FOUND, re-list names and retry with the exact match instead of switching to the Windows mirror.
- Use the WSL Ubuntu checkout as the canonical working copy. Make source changes, builds, Git commits, and GitHub pushes from WSL; do not develop in the Windows mirror.
- Preserve branch refs; remove only auxiliary checkouts that are clean, task-owned, and no longer needed after delivery.
- At task completion, close browser tabs opened for the task, stop only services/processes started for it, and remove temporary files. Inventory `git worktree list` and inspect each checkout's branch and status before removing it. Remove task-created auxiliary checkouts once their work is delivered; preserve the canonical checkout and any checkout containing unrelated or uncommitted work. Never use broad `git clean` commands to achieve checkout cleanup.
- Never commit `.env.qa.local`, passwords, private keys, Cloudflare tokens, Firebase keys, or other secrets.

## Required delivery order

- For every completed application change, build and run relevant checks locally, review the changed flow, commit and push the exact commit, then deploy it to PRD through the official wrapper documented in the local private infrastructure setup. The wrapper invokes the app's deployment implementation. The deploy must preserve the Cloudflare Tunnel connector during origin updates and verify local API/Nginx health plus external HTTPS smoke checks for both the public site and ERP before reporting success. A 1033/530, timeout, wrong HTTP status, or unexpected page content means delivery is incomplete; investigate and recover, then repeat all checks. This is the required end of development, not optional. If a prerequisite, deploy, or health check fails, stop and report the blocker; do not claim delivery is complete.
- Before committing or pushing any UI change, manually validate the affected flow in the local HML browser at localhost:4200 with the dedicated QA account from the ignored `.env.qa.local` and the local API. Use the standardized local helper: start `python3 scripts/qa-login-helper.py`, open `http://localhost:4200/__qa-login`, and submit the embedded real ERP login form through the browser. The helper reads credentials locally and prefills the real form without exposing them to browser automation; Codex must submit the form and inspect the authenticated HML page itself. Do not ask the user to enter credentials. Never use production accounts or data for QA, and never echo QA credentials into chat, logs, screenshots, source, or commits. If local HML, the helper, or the QA account is unavailable, stop before push/deploy and report the blocker. Run local HML services natively in WSL using `backend/.venv`; do not use Docker.
- Do not deploy a commit that differs from `origin/main`. Preserve production data and configuration.

## Release notes

- After each successful PRD deployment, add concise, user-facing notes to RELEASE_NOTES.md and link the exact deployed commit on GitHub. Record only verified deployment dates; distinguish retroactive commit dates from deployment dates. Keep the README link to the notes easy to find.

## Project commands

- Frontend production build: `cd frontend && npm ci && npm run build -- --configuration production`
- Backend syntax check: `cd backend && python -m compileall -q app`
- Deploy only through the official wrapper specified by the local private infrastructure setup. It validates the private production connection and invokes the app implementation, which runs migrations, restarts application services, and checks health.

## Production server connection

- Production SSH host, user, port, application path, and identity key are private project configuration. Keep them outside Git.
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
- Use WSL Ubuntu on every development PC. Keep the public app checkout at `~/workspace/garagista/parts-erp-main`. The private infrastructure checkout location is machine-local configuration and must not be published. Follow `docs/development-setup.md` and its pinned runtimes; run `scripts/setup-local.sh` on each PC.
- Keep all real credentials, connection metadata, SSH private keys, production data, and backups outside Git. Never place them in the public app repository. Local app environment values belong in ignored `backend/.env`; production connection values belong in the machine-local private configuration directory with restrictive permissions.
- Connection checks and deploy procedures are defined in the local private infrastructure setup. Run its read-only connectivity check before the official wrapper. The public app repository contains an internal deployment implementation; do not bypass the private wrapper for routine deploys.
- Keep private production connection settings local to each PC. Use individually managed SSH credentials and verified `known_hosts`; never copy private keys between PCs or disable strict host-key checking.
- Before changing public files, inspect the diff and scan newly added content for secrets. A secret accidentally committed must be revoked at its issuer; deleting it from the latest revision does not remove it from Git history.
