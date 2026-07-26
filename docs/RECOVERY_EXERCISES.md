# Recovery Exercise Evidence

Production readiness is not proven by having a backup feature or a runbook in
a repository. Each exercise below needs a dated, access-controlled record that
names the environment, operator, result, elapsed recovery time, evidence link,
and follow-up owner. Do not put personal records, access tokens, private keys,
or source-document contents in the exercise record.

## Pre-authorisation exercises

The following can be rehearsed without an institution's data or endorsement:

1. Run the synthetic pilot rehearsal and retain its canonical report.
2. Rebuild the locked container in protected CI and verify the dependency SBOM.
3. Apply Alembic migrations to a fresh disposable database.
4. Run the PostgreSQL RLS rehearsal against an explicitly disposable database.
5. Validate that a production configuration with a missing identity, database,
   storage, or signing control fails before serving traffic.
6. Rehearse a withheld workflow rule and confirm no external delivery occurs.

## Institution-dependent exercises

The following remain release gates until an institution supplies owners,
credentials, infrastructure, and approval:

1. Restore an encrypted database backup into a segregated recovery environment
   and reconcile the restored audit records without exposing personal data.
2. Restore a versioned source document and verify its hash and release
   citations against a retained trace.
3. Revoke a subject and staff identity at the IdP, then prove that active
   sessions and API access are rejected within the agreed period.
4. Rotate a signing key, verify historical releases with their stored public-key
   snapshots, and publish a separately approved replacement release.
5. Simulate a failed destination delivery only after a durable outbox exists;
   prove retry, dead-letter alerting, operator decision, reconciliation, and
   safe replay.
6. Run a privacy and accessibility incident exercise using the named assisted
   route and escalation contacts.

An exercise that cannot be completed is evidence of an open risk, not a reason
to waive the control. The pilot charter determines which open risks stop shadow
processing.
