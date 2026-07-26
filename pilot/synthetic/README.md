# Synthetic Pilot Rehearsal Pack

This directory contains fictional policy material and synthetic subject facts.
It is a regression suite for the institutional reasoning runtime, not a model
of any real institution and not evidence for a real decision.

Run it with:

```powershell
python -m app.sdk.pilot_rehearsal `
  --policy pilot/synthetic/progression_policy.json `
  --suite pilot/synthetic/progression_cases.json `
  --output pilot/synthetic/reports/progression_rehearsal.json
```

The command compiles the policy afresh, evaluates each case through the normal
engine, and writes a canonical report containing input, policy, and trace
SHA-256 digests. A non-zero exit code means one or more expected outcomes no
longer match.

The pack covers a verified approval, a threshold failure, a missing-evidence
failure, and an ambiguity that must be routed to human review. It contains no
UCT material, personal data, institutional decision, or claim of endorsement.

`system_record_contract.json` and `system_records.csv` exercise the separate
one-way CSV validation and reconciliation boundary. They are fictional records
and do not connect to or update any external system.

`system_record_contract.json` and `system_records.csv` exercise the separate
one-way CSV validation and reconciliation boundary. They are fictional records
and do not connect to or update any external system.

For a real pilot, copy the structure into an access-controlled institutional
repository only after the policy owner has approved the source corpus, legal and
privacy owners have accepted the data boundary, and expected outcomes have been
independently checked. Do not commit live evidence or source documents here.
