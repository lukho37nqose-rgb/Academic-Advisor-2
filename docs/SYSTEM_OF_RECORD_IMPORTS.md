# System-Of-Record Import Boundary

## Purpose

The IRE does not replace an institution's system of record. It accepts a
one-way export only after a policy owner or integration owner has approved a
mapping from source columns to the minimal facts required by a decision domain.
The current adapter supports a CSV export because it is inspectable, portable,
and can be rehearsed without vendor credentials. It does not call a vendor API,
write back to the source system, or persist a file during validation.

## Contract and preview

An approved contract names:

- the source system and mapping revision;
- stable subject and source-record-version columns;
- an optional source as-of date;
- each allowed source column, target fact path, type, and requiredness;
- file-size and row limits.

`app.adapters.system_record_import` then creates an in-memory preview with
SHA-256 digests for both the exact CSV bytes and the mapping contract. It rejects
non-UTF-8 files, missing or duplicate headers, missing required fields, invalid
types, duplicate subject identifiers, malformed CSV, and row or size limits.
The preview is all-or-nothing: any issue blocks materialisation as downstream
evidence. Its serialised report intentionally excludes subject identifiers and
field values.

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

## Production integration gate

The reference frontend's **System Records** screen now collects this contract
with labelled fields and a dry-run upload, so institutional staff do not edit
JSON or Python. It offers only facts declared for the chosen domain, and the
API independently rejects any undeclared target. A real connector is not ready
until the system owner approves the source, identity matching,
incremental-export semantics, retry/idempotency behaviour, reconciliation owner,
retention, encryption, service account, and incident path. A successful preview
does not make an export authoritative, and it never creates an operative
decision without the separate evidence, policy-release, and human-governance
controls.
