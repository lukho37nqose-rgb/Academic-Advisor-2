# UCT Case Study: Threat Model

## Scope

This is a pilot threat model for an unapproved UCT case study. It is a
requirements document, not a claim that UCT has accepted the controls. It
should be reviewed with UCT's information-security, privacy, policy, and
student-support owners before data is supplied.

## Protected assets

- Authoritative policy documents, amendments, their hashes, and page citations.
- Drafts, approvals, signatures, compiled releases, and audit history.
- Personal evidence, claims, facts, reasoning traces, and support requests.
- Identity claims, role assignments, tenant/domain boundaries, service secrets,
  and signing keys.
- The availability and accessibility of an explanation and human-assistance
  route.

## Trust boundaries

1. A UCT identity provider issues staff and subject tokens; the IRE validates
   them but does not own the UCT identity lifecycle.
2. UCT systems of record remain the authority for personal data and operative
   outcomes; adapters must use approved, least-privilege connections.
3. Handbook ingestion crosses from untrusted PDF/OCR text to reviewed source
   evidence; it does not cross directly into a live release.
4. The deterministic evaluator consumes only accepted facts and signed releases.
   AI-assisted extraction or explanation cannot determine an outcome.
5. Public policy guides and assistance forms are deliberately separate from
   authenticated personal evidence and decision endpoints.

## Priority threats and required controls

| Threat | Required control | Pilot evidence |
| --- | --- | --- |
| Wrong, superseded, or altered rule source | Immutable object hash, edition/effective-date register, page citations, policy-owner review, signed release. | Source register and approval record. |
| Author releases their own policy | Separate author and approver roles enforced by the API and rehearsed with two identities. | Governance audit trail. |
| Two administrators publish against stale governance state | Per-domain Postgres transaction advisory lock; release, graph, and draft-state transition commit together. | Concurrent publication rehearsal. |
| A historic signature cannot be verified after key rotation | Release stores signed envelope, hash, named key ID, and public-key snapshot; auditor verifies the stored bundle. | Key-rotation and historical-verification drill. |
| OCR or AI introduces a rule that was never approved | OCR output stays `PENDING_REVIEW`; a reviewer accepts/corrects/rejects page text before it becomes source evidence. | OCR review events and sample review. |
| A subject sees another person's outcome | OIDC token validation plus tenant, domain, and stable subject-ID checks at every evidence, evaluation, and trace endpoint. | Authorisation tests and revocation rehearsal. |
| One institution can access another's data | Application tenant checks plus forced PostgreSQL RLS with transaction-local tenant context; serving role cannot be superuser or `BYPASSRLS`. | RLS design, migration, and negative tests with two tenants. |
| A replay creates duplicate decisions | Redis-backed idempotency key and request lock. | Retry/concurrency test. |
| Unapproved schema change or weak infrastructure reaches production | Startup fails without Postgres, Redis, object storage, OIDC, a valid signing key, and disabled automatic schema creation. Migrations run separately. | Deployment pipeline output. |
| Logging exposes a personal record | Correlation logging contains method, path, status, duration, and request ID only; do not log bodies, query strings, tokens, evidence, or free-text assistance messages. | Log review and retention configuration. |
| Browser or intermediary caches disclose a personal response | API responses are no-store and carry anti-framing, no-referrer, and no-sniff protections; production allows explicit HTTPS origins and hosts only. | Browser-header and ingress review. |
| Personal evidence is sent to an unapproved external AI provider | External AI is mock-disabled by default; production requires explicit enablement, a named institutional approval reference, and a bounded input size. | Privacy/procurement approval and provider-boundary test. |
| A person cannot access the digital explanation | Public policy guide where approved, accessible controls/citations, named support owner, service target, and equivalent assisted/offline route. | Accessibility and support-route test. |
| Misleading or harmful automated outcome | Shadow mode first; `NEEDS_MANUAL_REVIEW` for missing/disputed information; no live adverse decision without separate UCT approval. | Shadow comparison and incident drill. |
| A person cannot challenge an incorrect decision | Subject-owned review cases are bound to their trace, preserve the original record, require a reasoned response, and support correction evidence. | End-to-end subject and coordinator rehearsal. |

## Known open controls

These controls are intentionally not claimed as complete by the present codebase:

- PostgreSQL RLS is implemented, but UCT must provision and rehearse distinct
  migration, serving, and break-glass roles against its managed database. The
  RLS context is set by the serving application, so stronger isolation still
  requires tenant-specific credentials, isolated databases, or a separately
  authenticated data-access service.
- Managed backup restoration, key rotation, disaster recovery objectives,
  vulnerability management, and central security monitoring need environment-
  specific implementation and rehearsal.
- UCT data classification, cross-border/hosting constraints, records retention,
  and legal authority must be determined by UCT.
- Real handbook extraction quality, tables, amendments, and transitional rules
  remain empirical pilot work and require policy-owner verification.

No pilot may present these open controls as closed. They are release gates or
explicitly accepted risks owned by the relevant UCT authority.
