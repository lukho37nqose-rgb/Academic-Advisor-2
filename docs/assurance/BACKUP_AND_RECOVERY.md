# Backup and Recovery

The current executable recovery evidence is limited to synthetic rehearsal,
fresh migration verification, Postgres RLS rehearsal, and worker checkpoint
recovery. The full exercise requirements are in
[../RECOVERY_EXERCISES.md](../RECOVERY_EXERCISES.md).

A controlled pilot must produce a dated restoration report from an isolated
environment. It must show that a restored tenant has the expected releases,
public-key snapshots, signatures, source hashes, trace metadata, mappings,
cases, and audit history; that source-object references resolve privately; and
that resumed checkpoint work does not duplicate accepted pages or OCR review
records.

Do not accept a successful backup job as recovery evidence. Record the operator,
environment, input backup identifier, elapsed time, result, exceptions, and
follow-up owner without including personal data or secrets.

Use [OPERATIONAL_EXERCISE_EVIDENCE.md](OPERATIONAL_EXERCISE_EVIDENCE.md) and
`tools/validate_operational_exercise.py` to validate the redacted exercise
record before retaining it in the institution's evidence store.
