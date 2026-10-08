# Termux server audit — 2026-10-07

Production host: SSH alias `parts-erp-server`, LAN REMOTE_HOST:8022.
Infra changes use `deploy/termux/harden-host.sh`, staged from the committed
source; this is host provisioning, not an application release. It preserves
the deployed application and takes a restricted backup of host settings.
Run it again after a release that regenerates Nginx configuration.

## Verified before changes

- API, ARQ worker, Redis, Nginx and one Cloudflare tunnel are separate processes.
- 3581 MB RAM; approximately 1170 MB available and 1304 MB swap used.
- Worker is configured for 10 concurrent jobs; do not increase workers blindly
  on the SQLite-backed phone. More processes require load measurements and
  idempotency/concurrency review first.
- API and Redis bind loopback. Nginx was bound to all interfaces.
- SSH accepted passwords. Key authentication works.
- Termux:Boot installed; boot did not explicitly start runsvdir.
- SSH service was running but normally disabled (`down` marker).
- Watchdog had no supervisor, no timeout for monitor work, and concurrent
  start/stop could spawn competing tunnel supervisors.
- Private configuration and SSH authorized_keys have mode 600.
- Requests for .env, .git/config and the database return 404; users API returns
  401 without authentication.
- Available SSH log has no usable authentication history. This is not evidence
  of absence of intrusion.
- Android security patch reports 2022-05-01. This remains a significant risk.

## Changes

- Runit-supervised watchdog, singleton lock, checks every 30 seconds.
- Serialized start/stop, maintenance marker to prevent resurrection during deploy.
- Bounded health requests and monitor execution.
- Boot starts termux-services; SSH enabled persistently, key-only, shorter
  authentication timeout and bounded unauthenticated sessions.
- Nginx accepts only loopback, hides version, limits slow clients, and applies
  a shared login limiter to both domain virtual hosts.
- Watchdog supervisor logs rotated by svlogd (1 MB, five archives).

## Limits / remaining work

- No guarantee against all failures, intrusions or DDoS. No destructive traffic
  test or Android reboot was performed on the live sales system.
- Process checks recover exited processes, not every hung application. The API
  health route is shallow, not a transaction-level readiness test.
- Confirm actual Cloudflare account WAF/rate-limit rules and firewall/router
  ingress settings. Public Cloudflare headers do not prove those settings.
- Boot after a real reboot and Android battery exemption remain unverified.
- Replace/upgrade the unsupported Android host for a maintained OS; phone,
  Wi-Fi, power and router remain single points of failure.
- Restore-test encrypted off-device backups. Local backups are not disaster recovery.
- Application logs need size-based rotation; historical worker log contains
  validation errors requiring separate application-level investigation.

Official references:
- https://github.com/termux/termux-boot
- https://github.com/termux/termux-services
- https://developers.cloudflare.com/fundamentals/security/protect-your-origin-server/
- https://developers.cloudflare.com/ddos-protection/best-practices/proactive-defense/
