# Institutional Deployment Rehearsal Contract

This document defines what is required to run the current rehearsed Cacisa
stack in an institutional non-production environment. It is operational
handoff material, not a claim that the product is production-ready.

## Evidence Boundary

The repository has already exercised the following in CI:

- the application container starts in production mode;
- PostgreSQL 15.18 runs with Alembic migrations applied separately;
- the runtime database role is restricted and PostgreSQL RLS tests execute;
- production authentication fails closed when OIDC/JWKS settings are missing;
- SQLite and development authentication fallbacks are rejected in production;
- frontend production build and Playwright checks pass;
- `/health/live`, `/health/ready`, public policy listing, and anonymous
  protected-route rejection run against the production-mode container.

The following remain institutional-environment checks:

- DNS and TLS for the institution-owned frontend/API origins;
- real institutional OIDC login and token validation;
- institution-specific tenant, role, subject, and domain claim mapping;
- real Redis and object-storage connectivity and permissions, if the selected
  pilot capability set uses those paths;
- institution-approved synthetic test users and test data.

## Pilot Dependency Classification

| Dependency | Classification | Code evidence | Current evidence state |
| --- | --- | --- | --- |
| PostgreSQL | Required for current pilot operation | `app/infrastructure/database.py`, Alembic migrations, subject, review, governance, evidence, release, and trace repositories | CI exercised with PostgreSQL 15.18, Alembic head, RLS, append-only controls |
| Institutional OIDC/JWKS | Required for current pilot operation | `app/services/auth.py`, `app/services/access_controls.py`, `frontend/src/authConfig.ts` | Production fail-closed exercised; real institutional login requires institutional execution |
| DNS/TLS | Required for institutional deployment | `app/services/http_safety.py`, frontend API base URL guardrails | Configuration checked; real DNS/TLS requires institutional environment |
| Redis | Required for bounded enabled capabilities: public assistance rate controls and idempotent write/evaluation guards | `app/services/access_controls.py`, `app/infrastructure/idempotency.py`, `app/api.py` release/evaluation lock usage | Configuration shape checked; real Redis behavior remains institutional/protocol rehearsal unless explicitly added |
| Object storage | Required for bounded enabled capabilities: durable evidence/source byte preservation, direct handbook uploads, replay/evaluation source-byte verification | `app/infrastructure/blob_storage.py`, `app/adapters/evidence.py`, handbook upload routes, evaluation/replay integrity checks | S3 configuration shape checked; S3-compatible/AWS behavior requires a live object-store rehearsal |
| Governance signing key | Required for current pilot operation that publishes releases or verifies release integrity | `app/core/crypto.py`, `app/services/release_integrity.py`, release routes | Static parsing checked; key custody remains institutional |
| External AI/OCR providers | Not required for current pilot core; optional governed capability | `app/services/ai_safety.py`, `app/services/ocr_provider.py` | Fail-closed configuration checks only |

Redis and object storage are not required merely to render an already-existing
student Current Position page. They become required when the deployed capability
set includes public assistance, idempotent protected writes/evaluation, governed
evidence/source intake, direct handbook uploads, or source-byte replay checks.

## Readiness Semantics

`GET /health/live` proves the application process can respond.

`GET /health/ready` proves database readiness for the core API process:

- the database connection succeeds;
- in production, the applied Alembic version matches the single reviewed head.

`/health/ready` does not prove real institutional OIDC login, Redis command
execution, object-storage access, DNS/TLS, backup/restore, or institutional
approval. Optional capability dependencies must be proven by smoke checks for
the selected capability set instead of being hidden behind a generic ready
response.

## Production Preflight

Run this before attempting a deployment rehearsal:

```powershell
python tools/production_preflight.py
```

By default the preflight checks the current pilot capability set:

```text
core, public-assistance, idempotent-writes, source-intake
```

For a narrower rehearsal, pass explicit capabilities:

```powershell
python tools/production_preflight.py --capability core
python tools/production_preflight.py --capability core --capability source-intake
```

The preflight validates static configuration only. It does not make live calls
to the IdP, Redis, PostgreSQL, or object storage.

It returns non-zero on failure and does not print credential values.

## Institutional OIDC Contract

Cacisa code requires:

- `JWT_JWKS_URL`: credential-free HTTPS JWKS endpoint;
- `JWT_ISSUER`: credential-free HTTPS issuer value used for token validation;
- `JWT_AUDIENCE`: API audience/client identifier expected in tokens;
- allowed signing algorithms: `RS256`, `RS384`, `RS512`, `ES256`, `ES384`,
  `ES512`;
- token claims `exp`, `iss`, `aud`, and `sub`;
- `IRE_TENANT_CLAIM`: claim containing a non-empty tenant identifier;
- `IRE_ROLE_CLAIM`: claim containing one Cacisa role value;
- `IRE_DOMAIN_IDS_CLAIM`: claim containing a list of domain identifiers;
- `IRE_SUBJECT_ID_CLAIM`: claim containing the subject identifier for student
  identities;
- optional `IRE_DELEGATION_CLAIM`: object containing delegated staff access,
  domain IDs, actor reference, and timezone-aware expiry.

The institution must supply:

- the actual non-production issuer and JWKS URL;
- the actual API audience/client identifier;
- frontend tenant OIDC values in `frontend/.env.tenant.example` shape:
  `VITE_OIDC_AUTHORITY`, `VITE_OIDC_CLIENT_ID`, `VITE_OIDC_SCOPE`, and
  `VITE_OIDC_AUDIENCE`;
- redirect URI(s) and post-logout URI(s) registered with the institution's IdP;
- a stable subject identifier claim for test students;
- a tenant claim value agreed for the rehearsal tenant;
- a role claim that emits Cacisa role values directly, or an institutional IdP
  transformation that maps groups to those values before tokens reach Cacisa;
- test users for at least subject, staff, approver, auditor, and tenant-admin
  paths, with domain assignments.

The current code does not implement a separate group-to-role mapping table.
Group mapping must therefore be done by the IdP/token issuer or by supplying a
claim whose value is already one of Cacisa's role names.

## Deployment Sequence

Use this order:

```text
provision dependencies
        ->
run production preflight
        ->
run Alembic with migrator credentials
        ->
start application with runtime credentials
        ->
wait for /health/live and /health/ready
        ->
run institutional smoke checks
```

Application replicas do not own migration execution. Run:

```powershell
python -m alembic upgrade head
```

with the migration principal before starting the serving container. The serving
container must use the restricted runtime database role.

Rollback currently means redeploying the previous reviewed image and operating
against the already-migrated database state, or applying a reviewed forward
recovery migration. Do not assume automatic schema rollback exists.

## Institutional Smoke Check

After deployment, run:

```powershell
python tools/institutional_smoke_check.py `
  --frontend-url https://<institution-frontend-origin> `
  --api-base-url https://<institution-api-origin>
```

Without a real token, the script checks DNS/TLS-shaped URLs, frontend
reachability, liveness, and readiness, then reports institutional OIDC as
blocked.

After completing a real institutional login and obtaining an approved test
access token, run:

```powershell
python tools/institutional_smoke_check.py `
  --frontend-url https://<institution-frontend-origin> `
  --api-base-url https://<institution-api-origin> `
  --access-token <institution-test-access-token>
```

The token is never printed by the script. With a token, the smoke check covers:

- protected session capabilities;
- tenant/role/domain claim mapping as exposed by capabilities;
- student Current Position;
- Student Information provenance;
- decision-review listing.

Decision-review submission requires a synthetic decision trace with agreed test
data. Do not use real student data unless the institution has approved it.

## Cacisa Supplies

- application container behavior and startup checks;
- required API port and health/readiness routes;
- Alembic migration command and separation from app startup;
- environment variable names and validation;
- PostgreSQL role expectations;
- preflight and smoke-test scripts;
- CI evidence for the current rehearsed stack.

## Institution Supplies

- non-production compute/container environment;
- PostgreSQL database and separate migrator/runtime credentials;
- OIDC application/client registration and test users;
- DNS/TLS for frontend and API origins;
- secrets mechanism for runtime environment values;
- Redis only if public assistance or idempotent write/evaluation capabilities
  are enabled;
- private object storage only if source/evidence intake, direct handbook
  upload, or source-byte replay capabilities are enabled;
- network routes from the application to selected dependencies;
- approval for synthetic test data and any institutional logs/telemetry.

## Later-Stage Needs Not Implemented Here

This contract does not implement Kubernetes, autoscaling, CDN, full monitoring,
PagerDuty, multi-region deployment, backup orchestration, workflow dispatcher,
PDF sandbox, provider frontend expansion, or speculative connectors.
