# Parts ERP project workflow

## Canonical development environment

- Use the WSL Ubuntu checkout of `parts-erp-main` as the canonical working copy. On the current Windows host it is `/home/fgoes/workspace/garagista/parts-erp-main`; locate the equivalent checkout on other hosts.
- Make source changes, builds, Git commits, and GitHub pushes from WSL. Do not develop in the Windows mirror and copy the result into WSL or production.
- Keep any separate parts-erp checkout and its branches intact; they may contain independent Termux/server work.
- The dedicated local visual-QA account is `qa-admin@example.com`; its password is kept only in the ignored `.env.qa.local` file. Never commit that file or use this account against production.

## Required delivery order

The default expectation for every completed application change is production delivery. Do not stop at a local build or GitHub push unless the user explicitly says not to deploy. After verification and push, deploy the exact pushed commit to production and report the public health result. If deployment is blocked by an external failure, keep the change documented and report the blocker clearly instead of silently treating the task as complete.

For application changes, complete these steps in order:

1. Implement and build locally in WSL.
2. Open the local ERP in a browser and manually inspect the changed flow. Use the dedicated local QA account and local-only data; do not ask the user to log in repeatedly or use production credentials. Check desktop and mobile layouts when the change affects UI. Do not claim visual verification unless the local screen was actually inspected.
3. Fix any issues found and repeat the local build and browser review. Automated test suites are optional: use them when they materially help validate backend/business logic or prevent a concrete regression, but do not make E2E automation a routine gate for visual changes.
4. Commit and push the verified change to GitHub.
5. Only after the local build, browser review, and GitHub push succeed, deploy the matching commit to the Termux production server. Keep production data and configuration intact; use the repository's deployment scripts and verify service health after deployment.

Never use production as the first place to build or discover UI problems. Do not deploy a commit that differs from the one verified locally and pushed to GitHub. If local browser verification or GitHub push is blocked, stop before production deployment and report the blocker.

## Project commands

- Frontend production build: `cd frontend && npm ci && npm run build -- --configuration production`
- Optional backend regression checks: `cd backend && pytest`
- Backend syntax check: `cd backend && python -m compileall -q app`
- Read deployment and server constraints in `deploy/termux/` before changing production deployment behavior.

## Production server connection

- The production host is the user's Android/Termux server, available through the SSH alias `parts-erp-server`.
- Use the configured SSH key/alias from the machine; never put passwords, private keys, Cloudflare tokens, Firebase keys, or other secrets in this file or in Git.
- Connection parameters are: SSH host alias `parts-erp-server`, port `8022`, application directory `~/parts-erp` (absolute path on Termux: `/data/data/com.termux/files/home/parts-erp`).
- Read-only connectivity check: `ssh -o BatchMode=yes -o ConnectTimeout=8 parts-erp-server "echo ssh-ok"`.
- Production health check: `ssh parts-erp-server "curl -fsS http://127.0.0.1:8080/health"`.
- Deploy only through `deploy/update-s9.sh`; it requires a clean checkout exactly matching `origin/main`, builds the frontend, validates required modules, uploads a staged release, runs migrations, restarts Termux services, and checks health.
- Do not use ad-hoc `scp`/manual overwrites for normal releases. If emergency access is required, preserve a backup and document the reason in the task before changing production.

## Shared period filters

- Use `frontend/src/app/shared/period-filter.ts` for date-range filtering in dashboard, invoices, monitoring, and future pages. Do not create page-specific copies of quick presets, custom date inputs, or range validation.
- The shared component owns the preset list and date-input behavior; pages provide labels/default ranges and handle the emitted range. Pass status options only when that page needs an additional status filter (as invoices do).
- Keep the shared component responsive and validate it in browser at desktop and mobile widths whenever its markup or styles change.

## Android APK releases

- The current, versioned Android installers live on the Termux server in `~/parts-erp/data/apks/`. This directory survives normal deployments. `latest.apk` and `latest.json` point to the newest published build. Access these files only over authenticated SSH; do not add a public download route or upload the APK to GitHub.
- After building and signing a new APK, commit and push its source and deploy that exact commit. Then run `deploy/publish-apk-s9.sh /absolute/path/to/signed.apk` with the same `S9_*` SSH variables as `deploy/update-s9.sh`. The publisher verifies package, version, signature, SHA-256, and exact Git commit before publishing atomically. Confirm the remote APK, manifest, and SHA-256 over SSH.
- Keep `frontend/android/app/google-services.json`, the Android signing keystore and its password out of Git and off the public server. The Firebase config and signing key must be obtained securely on each build machine. An APK signed with a different key cannot update an installed APK with the same package name.
