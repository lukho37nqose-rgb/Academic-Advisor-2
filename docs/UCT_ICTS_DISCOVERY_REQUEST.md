# UCT ICTS Discovery Request

This is a preparation document for possible UCT Humanities controlled
pre-production validation. It
does not claim UCT approval, affiliation, or authority to process UCT records.
It converts the technical dependencies into questions ICTS and institutional
owners can answer.

## Scope Requested

A non-production, non-operative validation environment for one bounded
Humanities decision. The environment must not write back to PeopleSoft,
Amathuba, email, student records, or any other UCT system.

## Identity

Please confirm whether ICTS can provide:

- OIDC or SAML integration path for a non-production application;
- issuer, audience, JWKS URL, and token lifetime;
- stable subject identifier claim;
- tenant, role, and domain/group assignment claims;
- at least three test identities covering subject, staff/policy editor, and
  independent approver or auditor;
- revocation test procedure.

## Hosting And Deployment

Please confirm the approved boundary for:

- non-production AWS account or approved hosting route;
- DNS and HTTPS/TLS route;
- managed PostgreSQL;
- Redis or equivalent approved cache service;
- private object storage with versioning and Object Lock or equivalent
  immutability for policy sources;
- secrets manager;
- remote Terraform state;
- separate migration, application, and break-glass database identities.

## Source Systems

For the first validation phase we are requesting read-only source-system
discovery where ICTS approves it, with file-based fallback where direct
connector access is not yet approved. We are not requesting write-back. Please
confirm the approved path for:

- PeopleSoft transcript or academic-record fields needed by the bounded
  decision;
- Amathuba attendance, coursework, DP/DPR, or assessment fields only if the
  chosen decision actually requires them;
- recorded historic outcomes, if privacy approval permits de-identified
  calibration cases.

For each export, the required answer is the field list, owner, refresh date,
record-state meaning, and whether it is authoritative, working, or reference
material.

## Operational Controls

Please identify the owner or approval path for:

- retention schedule for sources, facts, traces, reports, and review cases;
- privacy/security review;
- malware or document-safety scanning;
- backup retention and restore rehearsal;
- monitoring and alert triage;
- incident contact and escalation route;
- accessibility testing and assisted/offline support route;
- review or appeal handoff for missing evidence or source errors.

## Preflight Artefact

The answers above should be captured in a completed copy of
[`pilot/uct_humanities/institutional_shadow_manifest.template.json`](../pilot/uct_humanities/institutional_shadow_manifest.template.json),
stored outside Git. The repository preflight command is:

```powershell
python -m app.sdk.pilot_preflight --manifest C:\secure\path\institutional_shadow_manifest.json
```

A passing preflight means the validation phase has named owners and safe
technical boundaries. It does not make the system an operative UCT decision
system.
