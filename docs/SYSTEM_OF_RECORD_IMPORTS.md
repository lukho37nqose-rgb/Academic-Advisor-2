# System-Of-Record Import Boundary

## Purpose

The IRE does not replace an institution's system of record. It accepts source
records only after an authorised editor has submitted, and a different
authorised reviewer has approved, a mapping from source fields to the minimal
facts required by a decision domain.
The current adapter supports CSV because it is inspectable, portable, and can
be rehearsed without vendor credentials. CSV is the fallback and test-fixture
path, not the enterprise end state. The enterprise path is read-only connector
access to an institution-approved source, with the same independent source and
mapping review before records can become evidence. Neither path writes back to
the source system.

## Governed mapping configurations

The **System Records** staff screen lets an institution author a mapping using
labelled inputs and facts declared by the chosen decision domain. No JSON or
Python editing is required. Submitting the configuration creates an immutable
`PENDING` mapping record and a `SUBMITTED` audit event. A `approver` or
tenant administrator assigned to that domain can inspect the source columns and
decision facts, then approve it or reject it with a required reason.

An author cannot call a review endpoint, and the database rejects self-review
even if an application-layer role check is bypassed. A mapping can transition
only once from `PENDING` to `APPROVED` or `REJECTED`; its configuration and
SHA-256 contract digest cannot be changed afterwards. Events are append-only on
PostgreSQL and may be inserted only as the initial submission event or the
matching attributed terminal-review event. Both mapping tables have forced tenant row-level security, so a
serving connection can read or write only the tenant and domain named in its
request context.

The mapping record contains configuration metadata only: source field names,
fact
paths, type rules, reviewer attribution, timestamps, notes, and the contract
digest. It does not retain CSV bytes, connector payloads, subject identifiers,
source-record values, or a reconciliation snapshot. A rejected mapping is
corrected by submitting a new configuration, never by editing the historical
one.

## Contract and preview

A mapping contract names:

- the source system and mapping revision;
- stable subject and source-record-version columns;
- an optional source as-of date;
- each allowed source column, target fact path, type, and requiredness;
- file-size and row limits.

`app.adapters.system_record_import` then creates an in-memory preview with
SHA-256 digests for both the exact source bytes and the mapping contract. It rejects
non-UTF-8 files, missing or duplicate headers, missing required fields, invalid
types, duplicate subject identifiers, malformed CSV, and row or size limits.
The preview is all-or-nothing: any issue blocks materialisation as downstream
evidence. Its serialised report intentionally excludes subject identifiers and
field values. A preview is a dry run, not evidence ingestion; an approved
mapping is necessary configuration for a future import workflow but is not by
itself authority to create a decision.

Run the fully fictional example with:

```powershell
python -m app.adapters.system_record_import `
  --contract pilot/synthetic/system_record_contract.json `
  --csv pilot/synthetic/system_records.csv `
  --output pilot/synthetic/reports/system_record_preview.json
```

The synthetic files contain no institutional data and are a regression fixture,
not a template for a real policy or data model.

## Reconciliation

Before a later export can replace an accepted snapshot, compare both previews
with `reconcile_system_record_previews`. It reports counts of unchanged, added,
changed, and removed records. Any difference requires human approval. Subject
identifiers are available only in memory to an authorised integration process;
they are excluded from serialised reconciliation output to avoid turning an
operational report into a new personal-data store.

## Enterprise connector gate

The reference frontend's **System Records** screen now creates and reviews this
contract with labelled fields and a dry-run upload, so institutional staff do
not edit JSON or Python. It offers only facts declared for the chosen domain,
and the API independently rejects any undeclared target. A production connector
is not enabled until the system owner approves the source, identity matching,
incremental-export semantics, retry/idempotency behaviour, reconciliation owner,
retention, encryption, service account, and incident path. A successful preview
does not itself make a source authoritative. A confirmed record materialised
through an independently approved mapping creates accepted facts with that
mapping review as its recorded acceptance authority. Provisional records,
uploads, OCR, and manually entered information remain held evidence and require
ordinary independent fact review. Neither path publishes policy or makes a
decision during import.
