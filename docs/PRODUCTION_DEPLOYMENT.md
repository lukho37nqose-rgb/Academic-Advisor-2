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
   Deploy only from the reviewed `requirements.txt` hash lock and its committed
   `sbom.cdx.json` CycloneDX inventory. `requirements.in` is source intent only;
   it is not a deployable dependency manifest. Container and local
   infrastructure image references are pinned by digest and updated through
   reviewed automation.
3. Run `python -m alembic upgrade head` as a separate, reviewed deployment job
   using a migration principal. The serving container must not migrate its own
   schema.
4. Deploy the non-root application image. Check `/health/live` for process
   liveness and `/health/ready` for database readiness. Both return an
   `X-Request-ID` that can join a support report to safe request telemetry.
5. Deploy the durable handbook worker separately with an explicit
   `IRE_WORKER_TENANT_IDS` allowlist. The worker uses the same restricted serving
   database identity and must not receive a cross-tenant bypass credential.
6. Run post-deploy checks with institutional test identities: OIDC claim mapping,
   role revocation, tenant/domain isolation, author/approver separation,
   release signature verification, source upload, independently reviewed fact
   acceptance, evidence-hash failure, verified replay, assistance route, a
   subject-owned decision-review case, and an idempotent retry.
7. Enable shadow traffic only after the policy, privacy, accessibility, and
   operational owners have accepted the pilot entry gates.

## Configuration and secret operations

- Rotate the governance signing key through a controlled release process. Each
  new release stores its signed envelope, payload hash, public-key snapshot, and
  `GOVERNANCE_KEY_ID`; verify historical releases after every rotation.
- Use workload identity for database/object-store access where available; do not
  place cloud access keys in images or browser code.
- Keep object storage private and scope application IAM access to
  `tenants/{tenant_id}/` prefixes. Configure lifecycle, export, and audit jobs
  against the same prefix so a tenant's evidence and source documents remain
  operationally separable without staff handling storage objects. Enable and
  test object versioning and write-once retention or Object Lock for evidence
  and handbook sources. The application re-verifies SHA-256 before evaluation
  and replay, but bucket immutability is an infrastructure control.
- Restrict migration, application, and break-glass database accounts to distinct
  credentials and least-privilege roles.
- Run handbook/OCR work through `background_jobs` with an explicit
  `IRE_WORKER_TENANT_IDS` allowlist, and run retention work per tenant. Do not
  use an unscoped worker query against a production RLS database. Monitor queue
  age, lease recovery, retry volume, and `DEAD_LETTER` records; a dead letter
  requires an operator decision, not silent replay.
- Set log retention and redaction rules before traffic is accepted. Request
  telemetry must exclude credentials, personal evidence, query strings, and
  free-text assistance messages. The API applies no-store, anti-framing,
  no-referrer, and content-sniffing protections to its responses; the ingress
  must provide TLS and equivalent controls for any institution-hosted frontend.

## Required monitors and drills

- Alert on readiness failures, request error rate, latency, Redis/idempotency
  failures, failed handbook workers, unreviewed OCR backlog, overdue assistance
  requests, authorisation denials, and release failures.
- Require the protected CI checks to pass before a deployment. They use
  read-only repository permissions, immutable action references, bounded job
  times, production dependency audit, schema migration verification, a locked
  non-root container build, and a PostgreSQL RLS rehearsal.
- Rehearse an identity-revocation event, signing-key rotation, source-policy
  rollback, bad release rejection, backup restoration, and privacy/security
  incident escalation.
- Review access assignments and open support requests at a cadence agreed with
  the institution.
- Run the retention scheduler at least daily and monitor both expired support
  requests and expired decision-review cases. The institution must approve the
  `DECISION_REVIEW_RETENTION_DAYS` setting before real casework begins.

## Explicit non-goals of this baseline

This baseline includes a durable worker queue for internal handbook source
processing. It does not implement a durable **external workflow** outbox and
managed dispatcher, full disaster recovery, centralised security monitoring, or
a live institutional integration. Workflow rules are deliberately withheld
rather than simulated; see [WORKFLOW_DISPATCH.md](WORKFLOW_DISPATCH.md). These
are visible release gates, not hidden behind an enterprise label. PostgreSQL
RLS is implemented, but must still be rehearsed with the institution's real
serving and migration roles.
