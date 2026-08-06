# Threat Model

This is the repository-level companion to the UCT case-study model in
[../UCT_THREAT_MODEL.md](../UCT_THREAT_MODEL.md). It records the safety claims
that can be tested without an institution's data.

| Threat | Current defence | Residual risk / gate |
| --- | --- | --- |
| Forged or stale identity | JWT issuer, audience, expiry, signing-algorithm, and claim validation; production configuration fails closed. | IdP group mapping, revocation timing, and key rotation need controlled-pilot rehearsal. |
| Cross-tenant access | API tenant checks and forced Postgres RLS using transaction-local context. | Tenant context is supplied by trusted application code; managed roles and connection-pool rehearsal remain required. |
| Cross-subject access | Subject ID must match trace/evidence subject ID. | Stable, non-reassigned institutional subject identifier required. |
| Self-approved rule or mapping | Author/reviewer separation and immutable status transitions. | Institutional assignment process and break-glass review required. |
| Policy or graph alteration | Canonical signed release bundle, cited-source manifest hash, and production evaluation-time verification. | Institution must verify that the cited sources are authoritative and current before approving a release. |
| Hostile or altered PDF | File/type/size checks, private content-addressed storage, worker hash verification, review-only OCR. | Malware scanning and real document-quality measurement are not delivered. |
| Worker interruption | Tenant-scoped durable queue, renewable leases, bounded retry, dead-letter retention, and page checkpoints. | Monitoring, operator ownership, and external workflow delivery controls remain institution-dependent. |
| Sensitive logging | Header/body-safe middleware and telemetry redaction. | Central immutable audit store and alert triage are deployment controls. |
| Browser misuse or URL guessing | Capability-gated UI plus API role/domain/ownership checks. | Institution must configure the actual SSO frontend and session lifecycle. |

The system remains a transparency layer. It may explain the rule that caused a
case to require human review; it must not present a committee decision as if it
were made automatically.
