# Workflow Dispatch Boundary

Workflow rules are restricted, reviewed release content. They are included in
the signed release bundle alongside policy logic, effective dates, and
applicability selectors. When a signed rule matches an evaluation, the engine
creates a tenant-scoped `HELD` outbox record in the same database transaction as
the reasoning trace. It does not deliver anything to an institutional system
from an API process, a FastAPI background task, or an in-memory subscriber. The
compatibility `execute_workflow_actions` entry point returns
`DURABLE_DISPATCHER_REQUIRED` whenever a rule would have triggered. It does not
make a network call, invoke a webhook, or execute an action payload.

This is a safety control. A decision trace is an audit record; it must not
become an unacknowledged update to a student, finance, HR, admissions, or other
system merely because a test release contained a workflow rule.

## Required future implementation

Before any held record may be delivered, it needs all of the following:

- encrypted payload storage with a minimum necessary schema;
- a separate, authenticated worker with bounded retries, exponential backoff,
  dead-letter handling, and an operator replay decision;
- destination allowlisting, per-integration credentials, and a documented
  no-write validation mode;
- delivery receipts, reconciliation with the destination, and alarms for
  failures, duplicates, aged work, and dead letters;
- institutional system-owner approval, change window, privacy review, and a
  tested rollback or compensating-action process.

Until those controls are built and accepted, external workflow delivery is a
deployment blocker rather than an implied capability. Staff may author the
restricted rules through release review; matching evaluations create held
records only, and no person is asked to edit implementation data.
