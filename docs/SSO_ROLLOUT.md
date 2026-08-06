# SSO Rollout

IRE validates institutional OpenID Connect access tokens through the provider's
JWKS endpoint. The reference client uses authorization code plus PKCE through
the institution's approved identity provider. IRE does not operate a local
password store or issue production user credentials.

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

Production startup fails closed if the OIDC values, encrypted `rediss://` Redis,
or the public rate-limit salt are absent. JWKS and issuer URLs must be
credential-free HTTPS URLs. HS256 development tokens are refused in production.

## Claim contract

Every IRE token must contain:

| Claim | Purpose | Example |
| --- | --- | --- |
| `sub` | Immutable staff or person identity for audit events | `8ce2...` |
| `tenant_id` | Institution boundary | `university_a` |
| `role` | One IRE role | `staff_member` |
| `domain_ids` | Assigned decision domains | `["dom_support_2026"]` |
| `student_number` | Subject record binding where the role is `subject` | `S1234567` |

The claim names are configurable. Tenant and `sub` values must be non-empty;
domain assignments must be non-empty strings without duplicates. The subject
claim must be stable, non-reassigned, and match the subject identifier used by
the institution's system of record. A `subject` token can only submit evidence,
evaluate, or retrieve traces for that exact subject identifier.

## IRE role model

Map IdP groups to one of these six roles. The roles describe application
capabilities, not an institution's job titles; `domain_ids` restricts each
staff role to its authorised faculty, department, programme, or other decision
domain.

| Role claim | Intended responsibility |
| --- | --- |
| `subject` | View and challenge only their own institutional position. |
| `staff_member` | Day-to-day assigned-domain records, assistance, decision-review, cited-fact proposal, and low-risk metadata work. |
| `policy_editor` | No-code domain setup, policy drafting, source intake, mapping preparation, and calibration preparation. |
| `approver` | Independent fact/context attestation, interpretation resolution, mapping/calibration review, and release publication. Own work remains unapprovable. |
| `auditor` | Read-only review of authorised history, sources, traces, and controls. |
| `tenant_admin` | ICTS or designated system owner; monitored tenant setup and break-glass access. |

The former `metadata_steward`, `institutional_records_steward`,
`assistance_coordinator`, `rule_author`, `rule_approver`, and `policy_owner`
claims are no longer accepted. Update the IdP group mapping before deploying
this version; a rejected legacy role fails closed rather than receiving a broad
replacement role.

## Rollout checklist

1. Register the API audience and redirect origins with the institutional identity provider.
2. Map institutional groups to the smallest IRE role and domain assignments needed for each person.
3. Configure a separate non-human service identity only where scheduled operations require one; never reuse a staff identity.
4. Test issuer, audience, expiration, JWKS key rotation, disabled accounts, role removal, tenant separation, and subject-to-subject denial in staging.
5. Enable trusted proxy headers only when the API is behind the institution's controlled reverse proxy.
6. Rehearse an access revocation and an IdP outage before pilot launch.

The reference React client is configured only with public OIDC values:
authority, client identifier, scopes, optional API audience, redirect origin,
and post-logout redirect origin. It fails closed when those values are absent.
An institutional portal or access gateway may launch the same client, but the
browser must not invent roles, tenant identifiers, or domain assignments. IRE
remains responsible for validating the access token and enforcing its claims on
every protected API request.
