# Durable Background Worker

The API records handbook extraction and OCR work in the tenant-scoped
`background_jobs` table in the same database transaction that records the
source-state transition. The queue record contains a job type and source
identifier only. It never stores handbook text, policy data, evidence, or a
subject identifier.

Production AWS deployments may also configure
`IRE_BACKGROUND_JOB_SIGNAL_QUEUE_URL`. That SQS queue is a wakeup channel only:
messages contain the tenant, domain, job, job type, and resource identifiers so
workers can avoid slow polling. Workers still claim, lease, retry, and complete
jobs through PostgreSQL under tenant RLS. If SQS is unavailable, the worker logs
the signal failure and continues to poll the PostgreSQL ledger.

## Execution boundary

Run the worker separately from the API with the restricted serving database
credential and an explicit tenant allowlist:

```powershell
$env:IRE_WORKER_TENANT_IDS = 'tenant_uct_pilot'
$env:IRE_WORKER_ID = 'uct-pilot-worker-a'
$env:IRE_BACKGROUND_JOB_SIGNAL_QUEUE_URL = 'https://sqs.af-south-1.amazonaws.com/...'
python -m app.services.background_worker
```

In production, an empty `IRE_WORKER_TENANT_IDS` value is rejected. One worker
may serve several named tenants, but it claims and processes each job inside a
fresh tenant RLS scope. There is no global queue scan and no worker-specific
RLS bypass role.

## Lifecycle and operator response

1. `QUEUED`: eligible for a tenant worker.
2. `RUNNING`: leased to one named worker. The lease is renewed during long PDF
   processing.
3. `SUCCEEDED`: the worker reached a reviewable source or a human-review state.
   This never means a policy was created or published.
4. `DEAD_LETTER`: retry budget was exhausted or a lease repeatedly expired.
   Investigate the source, storage access, worker logs, and tenant scope before
   creating a new approved work item.

Only a `tenant_admin` can inspect identifier-only queue state through
`GET /api/v1/admin/background-jobs`. This is an operational observation route,
not a replay mechanism: it exposes no source text and cannot publish a policy.

Extraction has a bounded retry policy with exponential backoff. OCR deliberately
does not retry external-provider calls automatically: a provider problem returns
the source to an assisted/manual review path so the institution controls both
cost and accessibility.

## Local compose rehearsal

After applying migrations, start the worker profile:

```powershell
docker compose --profile migration run --rm migrate
$env:IRE_WORKER_TENANT_IDS = 'demo_university'
docker compose --profile workers up worker
```

This local command is not evidence of the institution-managed production queue.
The CI RLS rehearsal and the worker assurance tests are code evidence; queue
monitoring, alert routing, availability, and dead-letter ownership remain
institution-operated release gates.
