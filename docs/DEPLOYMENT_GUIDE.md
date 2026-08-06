# Future Deployment Guide

This guide is for the first institution-controlled deployment. It supplements
[PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md), which defines the
fail-closed runtime controls, and is intentionally sequenced so that no real
subject data is introduced before the relevant control is working.

## 1. Establish the deployment boundary

Before deploying, agree the pilot tenant, permitted decision domain, named
approver, staff-casework owner, privacy contact, retention
period, and an offline or assisted path for people who cannot use the portal.
For a UCT case study, use an explicitly approved policy subset and a synthetic
or de-identified rehearsal corpus first. Do not upload a real handbook or
student evidence merely to test the interface.

Record the institution's role mapping. Start with least privilege: policy
editors, staff members, independent approvers, auditors, subjects, and a
tightly controlled tenant-administrator account.
Avoid making a shared support mailbox or a service account a tenant
administrator.

## 2. Provision separate production roles

Provision these managed services in the institution's approved environment:

1. PostgreSQL, Redis, private encrypted object storage, a secrets manager,
   TLS ingress, central logging, metrics/alerts, and backup/restore storage.
2. An OIDC client for the API and the institution-hosted frontend using
   authorisation code plus PKCE. The frontend must not contain a client secret.
3. A migration principal, an application serving principal, and any worker
   principal as separate identities. The serving database role must not be a
   superuser or `BYPASSRLS` role. It must not create databases or roles.
4. Private storage permissions restricted to the application and worker tenant
   prefixes. Browser code must receive only scoped upload contracts, never
   storage credentials.

## 3. Configure identity before traffic

Configure OIDC/JWKS and map the institution's claims to the documented
contract in [SSO_ROLLOUT.md](SSO_ROLLOUT.md): `sub`, tenant, one IRE role,
assigned `domain_ids`, and a stable subject identifier for subject accounts.
Set the production values below through the secrets manager or workload identity,
not a repository file:

```text
IRE_ENV=production
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=rediss://...
JWT_JWKS_URL=https://idp.example.edu/.../jwks.json
JWT_ISSUER=https://idp.example.edu/
JWT_AUDIENCE=ire-api
IRE_TENANT_CLAIM=tenant_id
IRE_ROLE_CLAIM=role
IRE_DOMAIN_IDS_CLAIM=domain_ids
IRE_SUBJECT_ID_CLAIM=student_number
PUBLIC_RATE_LIMIT_SALT=<random secret>
GOVERNANCE_PRIVATE_KEY=<secret reference>
GOVERNANCE_KEY_ID=<institution key id>
S3_BUCKET_NAME=<private bucket>
IRE_AUTO_CREATE_SCHEMA=false
IRE_ALLOWED_HOSTS=<explicit HTTPS hostnames>
IRE_CORS_ALLOWED_ORIGINS=<explicit HTTPS frontend origins>
```

Configure the React reference client with only its API base URL and the
institution's approved token-acquisition mechanism. It must obtain the bearer
token through the institution's OIDC flow and call
`/api/v1/session/capabilities`; it must never decide a role from the email
domain or browser storage.

## 4. Build and verify the release artifact

Build from a clean reviewed commit. Install Python dependencies strictly from
the hash-locked `requirements.txt`, and verify the committed `sbom.cdx.json`.
Build the frontend and container in CI, where the protected checks run.

```powershell
python -m pip install --require-hashes -r requirements.txt
python -m pytest -q
python -m mypy --explicit-package-bases app

Set-Location frontend
npm.cmd ci
npm.cmd run lint
npm.cmd run build
```

Do not deploy a local SQLite database, an HS256 development token, a direct
database schema auto-create setting, or a container image that has not passed
the dependency, migration, frontend, and PostgreSQL RLS rehearsals.

## 5. Run migrations separately

Use the migration principal in a reviewed pipeline stage:

```powershell
python -m alembic upgrade head
```

Run the migration once per deployment, capture the Alembic revision and
migration logs, then deploy the non-root API and worker images with the serving
role. Do not allow an application container to migrate its own database on
startup. Apply and rehearse the RLS requirements in
[POSTGRES_RLS.md](POSTGRES_RLS.md) before connecting a real tenant.

## 6. Release in stages

1. Deploy to a staging tenant with no real personal data.
2. Verify `/health/live` and `/health/ready`, request IDs, TLS, security
   headers, object-store access, Redis, and non-bypass RLS behaviour.
3. Test OIDC issuer/audience validation, expired token rejection, role removal,
   domain reassignment, subject-to-subject denial, and direct-URL attempts at
   pages hidden by the capability response.
4. Test the governance path end to end: author a draft, reject self-approval,
   approve as another identity, verify its signature, and evaluate against an
   approved synthetic evidence item.
5. Test the user-safety paths: an offline assistance route, public support rate
   limit, subject-owned review request, retention scheduler, and a forced
   worker failure on a large handbook source.
6. Rehearse backup restoration, signing-key rotation, user revocation, source
   rollback, failed release handling, and security incident escalation.
7. Only then enable a limited, approved pre-production validation tenant. Keep
   external workflow writes disabled: the current workflow boundary is
   intentionally fail-closed.

## 7. Operate it as an institutional system

Review administrator assignments and domain scope regularly. Monitor readiness,
authorisation failures, RLS denials, release failures, handbook worker backlog,
OCR review backlog, overdue assistance/review cases, rate-limit events, and
retention-job failures. Keep logs free of credentials, evidence content, free-
text assistance messages, and query strings.

Any extension to a live system of record, an external workflow write, AI use on
institutional material, or a new decision domain should be a separately
reviewed deployment change with its own data-flow, privacy, RLS, recovery, and
human-oversight tests.
