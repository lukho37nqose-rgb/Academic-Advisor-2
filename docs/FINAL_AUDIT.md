# Historical Audit Snapshot - Superseded

**Original date:** July 2024
**Status:** Superseded by the current capability and deployment documents.

This document previously called a prototype a "Final Enterprise Engineering
Audit" while also saying that SQLite was the active database, the frontend was
not built, and operational workflow execution existed as a graph. It is kept
only to preserve project history. It is not an assurance report for the current
system.

## Corrections

- Production configuration rejects SQLite and requires PostgreSQL, OIDC/JWKS,
  Redis, object storage, signing material, and reviewed migrations.
- The repository has a reference React interface, but no completed browser SSO
  flow, IdP provisioning, or production role-administration interface.
- Workflow delivery is intentionally absent. No action is selected or sent by
  evaluation; a durable outbox/dispatcher remains a deployment blocker.
- Facts are no longer created by direct LLM extraction. A cited proposal needs
  independent acceptance and preserved evidence-hash verification.
- A replay endpoint now verifies source bytes, the signed release, accepted
  facts, the recomputed graph, and the stored decision summary.

## Current sources of truth

- [Current Capabilities](CURRENT_CAPABILITIES.md)
- [Production Deployment Baseline](PRODUCTION_DEPLOYMENT.md)
- [Workflow Dispatch Boundary](WORKFLOW_DISPATCH.md)
- [UCT Case Study Threat Model](UCT_THREAT_MODEL.md)

Use those documents, plus a deployment-specific assurance review, for any
institutional decision. They explicitly distinguish implemented controls from
controls that still require institutional ownership and rehearsal.
