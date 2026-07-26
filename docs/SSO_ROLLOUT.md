# SSO Rollout

IRE validates institutional OpenID Connect access tokens through the provider's JWKS endpoint. It does not operate a local password store or issue production user credentials.

## Required production configuration

Set these environment values before starting the API in `IRE_ENV=production`:

```text
JWT_JWKS_URL=https://idp.example.edu/.well-known/jwks.json
JWT_ISSUER=https://idp.example.edu/
JWT_AUDIENCE=ire-api
IRE_TENANT_CLAIM=tenant_id
IRE_ROLE_CLAIM=role
IRE_DOMAIN_IDS_CLAIM=domain_ids
IRE_SUBJECT_ID_CLAIM=student_number
REDIS_URL=rediss://...
PUBLIC_RATE_LIMIT_SALT=<long random secret>
```

Production startup fails closed if the OIDC values, Redis, or the public rate-limit salt are absent. HS256 development tokens are refused in production.

## Claim contract

Every IRE token must contain:

| Claim | Purpose | Example |
| --- | --- | --- |
| `sub` | Immutable staff or person identity for audit events | `8ce2...` |
| `tenant_id` | Institution boundary | `university_a` |
| `role` | One IRE role | `assistance_coordinator` |
| `domain_ids` | Assigned decision domains | `["dom_support_2026"]` |
| `student_number` | Subject record binding where the role is `subject` | `S1234567` |

The claim names are configurable. The subject claim must be stable, non-reassigned, and match the subject identifier used by the institution's system of record. A `subject` token can only submit evidence, evaluate, or retrieve traces for that exact subject identifier.

## Rollout checklist

1. Register the API audience and redirect origins with the institutional identity provider.
2. Map institutional groups to the smallest IRE role and domain assignments needed for each person.
3. Configure a separate non-human service identity only where scheduled operations require one; never reuse a staff identity.
4. Test issuer, audience, expiration, JWKS key rotation, disabled accounts, role removal, tenant separation, and subject-to-subject denial in staging.
5. Enable trusted proxy headers only when the API is behind the institution's controlled reverse proxy.
6. Rehearse an access revocation and an IdP outage before pilot launch.

The reference React client accepts a bearer token supplied by the host environment. An institutional portal, access gateway, or OIDC SPA should obtain that token through its approved authorization-code-with-PKCE flow; IRE remains responsible for validating the token and enforcing its claims.
