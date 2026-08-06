# Pilot Deployment Runbook

This runbook deploys three separately built frontends against one approved API.
It does not create an institution, identity provider, DNS zone, or certificate.
Those are supplied and approved by the pilot institution and platform owner.

## 1. Establish production identities

Create two OIDC applications:

- Tenant application: issues the existing tenant, role, domain, and subject claims.
- Provider application: issues only `sub` and `platform_role`, with values
  `platform_operator` or `platform_auditor`.

The provider issuer/audience must be different from every tenant issuer/audience.

## 2. Configure API secrets

Populate the Terraform runtime secret with tenant OIDC settings and:

```text
IRE_PROVIDER_JWKS_URL
IRE_PROVIDER_ISSUER
IRE_PROVIDER_AUDIENCE
IRE_PROVIDER_ROLE_CLAIM=platform_role
```

Set `IRE_CORS_ALLOWED_ORIGINS` to the exact HTTPS origins for `app`, `student`,
and `ops`. Do not use wildcard origins in production.

## 3. Apply database migrations

Run the migration task with the production database role before serving traffic:

```powershell
python -m alembic upgrade head
```

This includes row-level security, evidence currency, system-record idempotency,
and provider control-plane migrations. Confirm the API's production readiness
check passes before proceeding.

## 4. Deploy the API and workers

Build and publish the immutable API image, then run Terraform from
`deploy/terraform` with an approved AWS account and remote state. Apply only a
reviewed plan. The Terraform stack runs the API, migration task, worker, RDS,
Redis, encrypted evidence storage, and the API TLS endpoint.

## 5. Build and publish frontend surfaces

Build each frontend separately with its matching environment file:

```powershell
Copy-Item frontend/.env.tenant.example frontend/.env.production.local
npm --prefix frontend run build

Copy-Item frontend/.env.provider.example frontend/.env.production.local
npm --prefix frontend run build
```

Publish the resulting static assets to separate HTTPS origins:

- `app.<approved-domain>` for tenant staff;
- `student.<approved-domain>` for subjects;
- `ops.<provider-domain>` for provider operations.

Use separate CDN/site configurations and content-security policies. The provider
site must never share a tenant origin.

## 6. Verify before pilot access

- Authenticate a tenant staff account and confirm it cannot open `/provider/*`.
- Authenticate a provider account and confirm it cannot open tenant APIs.
- Confirm the provider page exposes only lifecycle and integration metadata.
- Run one approved CSV import with synthetic data; verify it creates evidence
  but no decision until fact acceptance.
- Confirm a subject sees only their own trace and provisional/confirmed wording.
