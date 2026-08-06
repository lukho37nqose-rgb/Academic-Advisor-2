# Deployment Surfaces

The platform is one product with separate deployments and authentication trust
boundaries. A tenant or subject token must never be accepted by the provider
control plane.

| Surface | Suggested hostname | Build setting | Identity provider |
| --- | --- | --- | --- |
| Public information | `www.example.org` | static public site | none |
| Institution workspace | `app.example.org` | `VITE_APP_SURFACE=tenant` | tenant OIDC client |
| Student portal | `student.example.org` | `VITE_APP_SURFACE=tenant` | tenant OIDC client |
| Provider operations | `ops.example.org` | `VITE_APP_SURFACE=provider` | provider OIDC client |
| Product API | `api.example.org` | API service | validates tenant and provider issuers separately |

The student and institution frontends may share a compiled codebase during the
pilot, but they should be deployed as separate origins with separate content
security policies and browser test suites. The provider frontend is a separate
build target and must use `VITE_PROVIDER_OIDC_*` settings.

In AWS, these surfaces should also map to different account or workload
boundaries. Public/demo/staging can be combined only before real institutional
data is present. A serious production tenant should have a dedicated AWS account
and should not share databases, buckets, queues, logs, or Terraform state with
the demo environment.

## Provider Control Plane

`ops.example.org` only calls `/api/v1/provider/*`. It can provision tenant
metadata, track lifecycle and integration status, and record a support-access
request. It intentionally does not expose evidence, student positions, policy
content, or decision traces.

Production requires separate provider OIDC configuration:

```text
IRE_PROVIDER_JWKS_URL=https://provider-idp.example.org/.well-known/jwks.json
IRE_PROVIDER_ISSUER=https://provider-idp.example.org/
IRE_PROVIDER_AUDIENCE=ire-provider-operations
IRE_PROVIDER_ROLE_CLAIM=platform_role
```

The supported provider roles are `platform_operator` and `platform_auditor`.
They are not tenant roles and must not be issued by an institution's identity
provider.

## Deployment Rule

Deploy each surface through CI after tests and approval. Do not use a provider
operations interface to modify source code, database rows, or tenant policies.
Terraform deploys the API and worker infrastructure; static frontend hosting,
DNS, TLS certificates, and OIDC applications must be supplied by the approved
production environment before a pilot goes live.

See `docs/AWS_PLATFORM_ARCHITECTURE.md` for the recommended AWS account model,
SQS/PostgreSQL worker boundary, provider operations boundary, and data-location
inventory.
