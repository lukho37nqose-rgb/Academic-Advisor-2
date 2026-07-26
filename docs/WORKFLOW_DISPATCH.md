# Workflow Dispatch Boundary

The IRE can identify policy-approved post-decision workflow rules, but it does
not deliver them to an institutional system from an API process, a FastAPI
background task, or an in-memory event subscriber. The legacy
`execute_workflow_actions` entry point now returns
`DURABLE_DISPATCHER_REQUIRED` whenever a rule would have triggered. It does not
make a network call, invoke a webhook, or execute an action payload.

This is a safety control. A decision trace is an audit record; it must not
become an unacknowledged update to a student, finance, HR, admissions, or other
system merely because a test release contained a workflow rule.

## Required future implementation

Before a workflow integration is enabled, it needs all of the following:

- a tenant- and domain-scoped transactional outbox written with the completed
  evaluation record;
- unique idempotency keys per release, reasoning trace, and workflow rule;
- encrypted payload storage with a minimum necessary schema;
- a separate, authenticated worker with bounded retries, exponential backoff,
  dead-letter handling, and an operator replay decision;
- destination allowlisting, per-integration credentials, and a documented
  no-write or shadow mode;
- delivery receipts, reconciliation with the destination, and alarms for
  failures, duplicates, aged work, and dead letters;
- institutional system-owner approval, change window, privacy review, and a
  tested rollback or compensating-action process.

Until those controls are built and accepted, external workflow delivery is a
deployment blocker rather than an implied capability.
