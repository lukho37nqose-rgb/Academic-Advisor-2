# Enterprise Safety Baseline

**Claim:** Enterprise Safety Baseline - Verified for Controlled Pilot

**Scope:** The repository, synthetic test fixtures, and disposable CI
infrastructure only. This does not claim a UCT deployment, UCT approval, or
handling of real institutional records.

## Assurance status

`Verified` means a control has a named enforcement point and executable test
evidence. `Partial` means a protective mechanism exists but a required part of
the control is not yet delivered. `Institution-dependent` means the code can
enforce the boundary only after the institution supplies infrastructure,
configuration, ownership, or approval.

| ID | Control | Risk addressed | Enforcement point | Failure behaviour | Verification evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |
| ESB-01 | Token validation and fail-closed production identity configuration | Forged, expired, or wrongly issued identity | `app/services/auth.py`, `app/services/access_controls.py` | Reject request or refuse startup | `tests/test_auth.py`, `tests/test_access_controls.py`, `tests/test_production_readiness.py` | Verified in development/CI; institutional OIDC remains required. |
| ESB-02 | Role, domain, ownership, and workspace controls | Unauthorised action or accidental use of a staff workflow | Route role dependencies, domain/subject checks, `/session/capabilities` | `403` or no authorised workspace | `tests/assurance/test_authorization_matrix.py`, `tests/test_session_capabilities_api.py`, decision-review tests | Verified. |
| ESB-03 | Tenant isolation with forced PostgreSQL RLS | Cross-institution disclosure or mutation | `app/infrastructure/database.py`, Alembic RLS migrations | Zero rows or database error | `tests/integration/test_postgres_rls.py`, CI job `postgres-rls-rehearsal` | Verified on disposable PostgreSQL. Real serving/migration roles remain institution-dependent. |
| ESB-04 | Subject ownership | One person viewing or submitting for another person | `ensure_subject_access` and subject-bound routes | `403` | `tests/test_evaluation_api.py`, `tests/test_decision_review_api.py`, `tests/assurance/test_authorization_matrix.py` | Verified. |
| ESB-05 | Separate policy authoring and approval | Self-approval or stale policy publication | Draft/release state checks and domain lock | `403` or `409` | `tests/test_governance_api.py`, `tests/test_safety_controls.py` | Verified. |
| ESB-06 | Signed release bundle and evaluation-time verification | Substituted release metadata, source manifest, policy, or compiled graph | `app/core/crypto.py`, `app/services/release_integrity.py`, evaluation route | Production evaluation rejects incomplete or invalid bundle | `tests/assurance/test_release_integrity.py`, `tests/test_safety_controls.py` | Verified for current release manifest. Institutional source authority remains a pilot gate. |
| ESB-07 | Private, content-addressed evidence and handbook sources | Object disclosure or silent source substitution | `BlobStorage`, tenant prefixes, source hashing, worker hash check | Upload/retrieval failure; source processing stops | `tests/test_blob_storage.py`, `tests/test_handbook_ingestion_api.py` | Verified for code paths. Bucket policy, malware scanning, and lifecycle rules are institution-dependent. |
| ESB-08 | Large-PDF checkpoint recovery and durable source queue | Duplicate, lost, or corrupted extraction after worker interruption | Tenant-scoped `background_jobs`, worker leases, bounded retries, dead-letter state, and handbook page checkpoints | Restart resumes from the next persisted page; unrecoverable work is retained as `DEAD_LETTER` | `tests/assurance/test_job_recovery.py`, `tests/assurance/test_background_jobs.py`, `tests/test_handbook_ingestion_api.py` | Verified for handbook source processing in CI. Institution-operated worker monitoring remains required. |
| ESB-09 | Separate migrations and fail-closed startup | Unsafe schema mutation or incomplete production configuration | Alembic, production-readiness and DB-role validation | Startup/deployment blocks | `tests/test_production_readiness.py`, `tests/integration/test_postgres_rls.py`, CI migration step | Verified in CI. Managed deployment pipeline remains institution-dependent. |
| ESB-10 | Correlation and sensitive-data redaction | Evidence or secrets leaking into logs | Request middleware and telemetry redaction | Sensitive fields redacted or omitted | `tests/test_safety_controls.py`, `tests/test_operational_api.py` | Partial: immutable database audit permissions and central SIEM are open. |
| ESB-11 | Recovery and retention controls | Unrecoverable or over-retained institutional data | Retention settings, recovery runbooks | Operational gate; no false completion claim | `docs/RECOVERY_EXERCISES.md`, `tests/test_public_access_api.py`, `tests/test_decision_review_api.py` | Institution-dependent. |

## Evidence procedure

Run the repository verification set from a clean checkout:

```powershell
python -m pip install --require-hashes -r requirements.txt
python -m pytest -q
python -m mypy --explicit-package-bases app tests

Set-Location frontend
npm.cmd ci
npm.cmd run lint
npm.cmd run build
```

CI additionally runs the browser suite, locked container build, fresh Alembic
migration, SBOM consistency check, and a disposable PostgreSQL RLS rehearsal.
Do not treat a local SQLite result as proof of the PostgreSQL control.

## Open pilot gates

The following are deliberately not marked closed by this baseline:

- institutional OIDC registration, group mapping, revocation behaviour, and
  test identities;
- managed PostgreSQL roles, backups, object-storage privacy policy, Redis
  availability, monitoring, and alert response ownership;
- institutional confirmation that each signed release source is authoritative,
  current, and approved for the pilot domain;
- durable outbox, reconciliation, and destination controls for any future
  external workflow delivery;
- approved retention schedule, data classification, accessibility review,
  incident contacts, and pilot governance;
- a real handbook extraction comparison against policy-owner-verified text.

No pilot should convert an open gate into an implied acceptance. Each needs a
named institutional owner, date, evidence location, and decision.
