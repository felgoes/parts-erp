# Parts ERP project workflow

## Canonical development environment

- Use the WSL Ubuntu checkout at `/home/underlocks/workspace/garagista/parts-erp-main` as the canonical working copy for this project.
- Make source changes, builds, Git commits, and GitHub pushes from WSL. Do not develop in the Windows mirror and copy the result into WSL or production.
- Keep the user's existing `/home/underlocks/workspace/garagista/parts-erp` checkout and its `fix/production-readiness` branch intact; it contains separate Termux/server work.

## Required delivery order

For application changes, complete these steps in order:

1. Implement and build locally in WSL.
2. Run the relevant automated checks and inspect the changed flow in a browser against the local build. Check desktop and mobile layouts when the change affects UI. Do not claim visual verification unless the local screen was actually inspected.
3. Fix any issues found and repeat the local build and visual review.
4. Commit and push the verified change to GitHub.
5. Only after the local build, checks, visual review, and GitHub push succeed, deploy the matching commit to the Termux production server. Keep production data and configuration intact; use the repository's deployment scripts and verify service health after deployment.

Never use production as the first place to build or discover UI problems. Do not deploy a commit that differs from the one verified locally and pushed to GitHub. If local visual verification or GitHub push is blocked, stop before production deployment and report the blocker.

## Project commands

- Frontend production build: `cd frontend && npm ci && npm run build -- --configuration production`
- Backend checks: `cd backend && pytest`
- Backend syntax check: `cd backend && python -m compileall -q app`
- Read deployment and server constraints in `deploy/termux/` before changing production deployment behavior.
