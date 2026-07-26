# Production Deployment Baseline

## Purpose

This runbook defines the minimum operational boundary for a controlled
institutional pilot. It is not a one-command production deployment guide. A
deployment is incomplete until the institution has supplied its own identity,
hosting, privacy, monitoring, backup, incident-response, and change-management
controls.

## Fail-closed startup checks

When `IRE_ENV=production`, application startup rejects a deployment unless all
of the following are configured:

- OIDC/JWKS validation settings: `JWT_JWKS_URL`, `JWT_ISSUER`, and
  `JWT_AUDIENCE`;
- Redis and a non-placeholder `PUBLIC_RATE_LIMIT_SALT` for public assistance
  protection and idempotency;
- a `postgresql+asyncpg` database URL, never SQLite;
- the reviewed PostgreSQL RLS migration, plus a serving role that is neither
  superuser nor `BYPASSRLS` and cannot create database roles or databases;
- explicit `IRE_ALLOWED_HOSTS` and HTTPS-only `IRE_CORS_ALLOWED_ORIGINS`, with
  no wildcard host or browser origin;
- `IRE_AUTO_CREATE_SCHEMA=false`;
- an object-storage bucket and encryption setting;
- a parseable private key in `GOVERNANCE_PRIVATE_KEY` and a named
  `GOVERNANCE_KEY_ID` for signing releases.

The checks prove configuration is present, not that an external service is
reachable or that a control has been approved. Deployment automation must test
connectivity and permissions with a non-production health check before traffic
is switched.

## Required deployment sequence

1. Provision managed Postgres, Redis, object storage, identity-provider client,
   secrets manager, TLS ingress, central log destination, metrics/alerting, and
   a backup/restore target.
2. Store only secret references or runtime-injected secrets in deployment
   configuration. Never commit private keys, access tokens, source PDFs, or
   personal evidence to this repository or an image layer.
3. Run `python -m alembic upgrade head` as a separate, reviewed deployment job
   using a migration principal. The serving container must not migrate its own
   schema.
4. Deploy the non-root application image. Check `/health/live` for process
   liveness and `/health/ready` for database readiness. Both return an
   `X-Request-ID` that can join a support report to safe request telemetry.
5. Run post-deploy checks with institutional test identities: OIDC claim mapping,
   role revocation, tenant/domain isolation, author/approver separation,
   release signature verification, source upload, assistance route, a
   subject-owned decision-review case, and an idempotent retry.
6. Enable shadow traffic only after the policy, privacy, accessibility, and
   operational owners have accepted the pilot entry gates.

## Configuration and secret operations

- Rotate the governance signing key through a controlled release process. Each
  new release stores its signed envelope, payload hash, public-key snapshot, and
  `GOVERNANCE_KEY_ID`; verify historical releases after every rotation.
- Use workload identity for database/object-store access where available; do not
  place cloud access keys in images or browser code.
- Restrict migration, application, and break-glass database accounts to distinct
  credentials and least-privilege roles.
- Run handbook/OCR workers with a tenant identifier in the trusted job payload,
  and run retention work per tenant. Do not use an unscoped worker query against
  a production RLS database.
- Set log retention and redaction rules before traffic is accepted. Request
  telemetry must exclude credentials, personal evidence, query strings, and
  free-text assistance messages. The API applies no-store, anti-framing,
  no-referrer, and content-sniffing protections to its responses; the ingress
  must provide TLS and equivalent controls for any institution-hosted frontend.

## Required monitors and drills

- Alert on readiness failures, request error rate, latency, Redis/idempotency
  failures, failed handbook workers, unreviewed OCR backlog, overdue assistance
  requests, authorisation denials, and release failures.
- Rehearse an identity-revocation event, signing-key rotation, source-policy
  rollback, bad release rejection, backup restoration, and privacy/security
  incident escalation.
- Review access assignments and open support requests at a cadence agreed with
  the institution.
- Run the retention scheduler at least daily and monitor both expired support
  requests and expired decision-review cases. The institution must approve the
  `DECISION_REVIEW_RETENTION_DAYS` setting before real casework begins.

## Explicit non-goals of this baseline

This baseline does not yet implement a managed job queue, full disaster
recovery, centralised security monitoring, or a live institutional integration.
Those are deliberately visible release gates, not hidden behind an enterprise
label. PostgreSQL RLS is implemented, but must still be rehearsed with the
institution's real serving and migration roles.
