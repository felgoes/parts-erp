# Parts ERP project workflow

## Canonical development environment

- Use the WSL Ubuntu checkout at `/home/underlocks/workspace/garagista/parts-erp-main` as the canonical working copy for this project.
- Make source changes, builds, Git commits, and GitHub pushes from WSL. Do not develop in the Windows mirror and copy the result into WSL or production.
- Keep the user's existing `/home/underlocks/workspace/garagista/parts-erp` checkout and its `fix/production-readiness` branch intact; it contains separate Termux/server work.
- The dedicated local visual-QA account is `qa-admin@example.com`; its password is kept only in the ignored `.env.qa.local` file. Use it only against local development/homologation, never production. Read credentials at runtime without printing, logging, screenshotting, or committing the password, access token, or `.env.qa.local` file.

## Required delivery order

For application changes, complete these steps in order:

1. Implement and build locally in WSL.
2. Open the local ERP in a browser, authenticate with the dedicated local QA account, and manually inspect the changed flow using local-only data. Do not substitute API-only checks, an unauthenticated login-page screenshot, or a production session for this browser review. Do not ask the user to log in repeatedly or use production credentials. Check desktop and mobile layouts when the change affects UI. Do not claim visual verification unless the authenticated local screen was actually inspected.
3. For changed workflows, exercise the actual UI path through the relevant screen and object details, and verify the resulting state and feedback. Never trigger real external side effects (for example, issuing a Mercado Livre NF-e, printing/downloading a live label, publishing an item, or changing live stock) as part of QA; use a mock, sandbox, or isolated local test data. If the QA account or local browser session is unavailable, repair the local-only QA setup or use an approved local test-session mechanism; do not make production the test environment.
4. Fix any issues found and repeat the local build and browser review. Automated test suites are optional: use them when they materially help validate backend/business logic or prevent a concrete regression, but do not make E2E automation a routine gate for visual changes.
5. Commit and push the verified change to GitHub.
6. Only after the local build, authenticated browser review, and GitHub push succeed, deploy the matching commit to the Termux production server. Keep production data and configuration intact; use the repository's deployment scripts and verify service health after deployment.

Never use production as the first place to build or discover UI problems. Do not deploy a commit that differs from the one verified locally and pushed to GitHub. If authenticated local browser verification or GitHub push is blocked, stop before production deployment and report the blocker; do not ask the user to perform routine QA login for you.

## Project commands

- Frontend production build: `cd frontend && npm ci && npm run build -- --configuration production`
- Optional backend regression checks: `cd backend && pytest`
- Backend syntax check: `cd backend && python -m compileall -q app`
- Read deployment and server constraints in `deploy/termux/` before changing production deployment behavior.

## Shared period filters

- Use `frontend/src/app/shared/period-filter.ts` for date-range filtering in dashboard, invoices, monitoring, and future pages. Do not create page-specific copies of quick presets, custom date inputs, or range validation.
- The shared component owns the preset list and date-input behavior; pages provide labels/default ranges and handle the emitted range. Pass status options only when that page needs an additional status filter (as invoices do).
- Keep the shared component responsive and validate it in browser at desktop and mobile widths whenever its markup or styles change.
