# Historical Audit Snapshot - Superseded

**Original date:** July 2024
**Status:** Historical architecture-pivot record. It is not a current audit or
an operational capability statement.

This file previously described an early prototype with no API, database,
idempotency handling, cryptographic implementation, request correlation, or
reference frontend. Those statements are no longer true and must not be used
for a procurement, security, pilot, or deployment decision.

## Historical observations and current position

| Historical observation | Current position |
| --- | --- |
| No HTTP routes or database | FastAPI routes, SQLAlchemy persistence, Alembic migrations, and PostgreSQL RLS are implemented. |
| No idempotency | Evaluation requires idempotency and scopes cache entries to tenant, caller, subject, operation, and canonical request body. |
| Signatures were theoretical | Releases are signed and their persisted verification bundles are checked before evaluation and replay. |
| No request correlation | Request IDs and safe request telemetry are implemented. |
| No frontend | A React reference client with server-issued role capabilities exists. It is not a completed institutional SSO or operational fact-review portal. |
| Evidence extraction drove facts directly | Evaluation now requires independently accepted, cited facts and re-verifies evidence hashes. |
| Replay was only an aspiration | The verifier recomputes a trace and checks its release, evidence hash, accepted-fact lineage, and summary. |

## Current sources of truth

- [Current Capabilities](CURRENT_CAPABILITIES.md)
- [Production Deployment Baseline](PRODUCTION_DEPLOYMENT.md)
- [Workflow Dispatch Boundary](WORKFLOW_DISPATCH.md)
- [UCT Case Study Threat Model](UCT_THREAT_MODEL.md)

The remaining open controls in those documents are real release gates. This
historical snapshot does not close them.
