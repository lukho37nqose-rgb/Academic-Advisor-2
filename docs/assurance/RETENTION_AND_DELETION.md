# Retention and Deletion

The code carries configurable retention expiry for public assistance and
decision-review cases. It deliberately does not infer an institution's legal
retention period. `SUPPORT_REQUEST_RETENTION_DAYS` and
`DECISION_REVIEW_RETENTION_DAYS` require institutional approval before real
casework.

Before a pilot, document for each data class: purpose, legal basis, owner,
retention duration, deletion method, backup treatment, subject-access route,
and preservation hold process. Configure object-storage lifecycle and deleted
record handling so database references, private objects, audit expectations,
and recovery requirements do not contradict each other.

Deletion is not considered complete until the primary store, derivatives,
exports, and lifecycle-managed object copies have been handled according to the
approved policy. Backups require a separately documented expiry or isolation
strategy.
