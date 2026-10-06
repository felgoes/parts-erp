# Parts ERP project workflow

## Canonical development environment

- Use the WSL Ubuntu checkout at `/home/underlocks/workspace/garagista/parts-erp-main` as the canonical working copy for this project.
- Make source changes, builds, Git commits, and GitHub pushes from WSL. Do not develop in the Windows mirror and copy the result into WSL or production.
- Keep the user's existing `/home/underlocks/workspace/garagista/parts-erp` checkout and its `fix/production-readiness` branch intact; it contains separate Termux/server work.

## Required delivery order

For application changes, complete these steps in order:

1. Implement and build locally in WSL.
2. Run relevant automated tests and production builds. Do not require local browser login, a disposable QA user, or manual visual review unless the user explicitly asks for it.
3. Never trigger real external side effects (for example, issuing a Mercado Livre NF-e, downloading a live label, publishing an item, or changing live stock) as part of QA; use mocks, sandbox, or isolated test data.
4. Commit and push the change to GitHub.
5. After the build/tests and GitHub push succeed, deploy the matching commit to the Termux production server when deployment is in scope. Keep production data and configuration intact; use the repository's deployment scripts and verify service health after deployment.

Do not deploy a commit that differs from the one built/tested and pushed to GitHub. If build/tests or GitHub push are blocked, stop before production deployment and report the blocker.

## Project commands

- Frontend production build: `cd frontend && npm ci && npm run build -- --configuration production`
- Optional backend regression checks: `cd backend && pytest`
- Backend syntax check: `cd backend && python -m compileall -q app`
- Read deployment and server constraints in `deploy/termux/` before changing production deployment behavior.

## Shared period filters

- Use `frontend/src/app/shared/period-filter.ts` for date-range filtering in dashboard, invoices, monitoring, and future pages. Do not create page-specific copies of quick presets, custom date inputs, or range validation.
- The shared component owns the preset list and date-input behavior; pages provide labels/default ranges and handle the emitted range. Pass status options only when that page needs an additional status filter (as invoices do).
- Keep the shared component responsive; perform visual browser validation when the user asks for it.
