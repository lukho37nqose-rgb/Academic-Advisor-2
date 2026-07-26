# Operational Exercise Evidence

Backups, identity revocation, and incident response are institution-operated
controls. This repository cannot claim that a real exercise occurred. It does
provide a redacted, machine-validated record format so an exercise produces
auditable evidence without copying personal records, source documents,
credentials, or private keys into the project.

Create the record in the institution's access-controlled evidence store, then
validate a temporary redacted export:

```powershell
python tools/validate_operational_exercise.py exercise-record.json
```

The record must include an exercise type, environment, timezone-aware time,
operator reference, result, elapsed time, evidence location, and at least one
reference. Failed or blocked exercises also require a follow-up owner. The
validator rejects obvious credential fields and private-key or bearer-token
material; it does not replace the institution's privacy review.

Supported exercise types are:

- `backup_restore`: restore an encrypted database backup and a versioned source
  object in an isolated recovery environment, then reconcile hashes, releases,
  and trace metadata.
- `identity_revocation`: remove a staff or subject access assignment at the IdP
  and demonstrate rejection within the agreed response period.
- `incident_response`: contain, preserve, assess, communicate, recover, and
  assign follow-up actions under the institutional incident process.
- `dead_letter_recovery`: investigate a durable handbook job that exhausted its
  retry budget, record the decision, and prove that no automatic policy change
  occurred.
- `signing_key_rotation`: verify historical signed releases with retained public
  keys, then issue a separately approved release under the replacement key.

Treat `FAIL` and `BLOCKED` as open pilot risks. A record of an exercise is
evidence, not a waiver.
