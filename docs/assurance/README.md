# Enterprise Safety Baseline

This directory is the assurance package for the claim **Enterprise Safety
Baseline - Verified for Controlled Pilot**. It is evidence of implemented,
tested controls. It is not an institutional certification, legal opinion, or
production approval.

Start with [ENTERPRISE_SAFETY_BASELINE.md](ENTERPRISE_SAFETY_BASELINE.md). Each
control has an identifier, an enforcement point, a failure mode, verification
evidence, limitations, and the owner or configuration needed before a real
institutional pilot.

| Document | Purpose |
| --- | --- |
| [ENTERPRISE_SAFETY_BASELINE.md](ENTERPRISE_SAFETY_BASELINE.md) | Canonical control register and evidence index. |
| [THREAT_MODEL.md](THREAT_MODEL.md) | Product-wide threat model and residual risks. |
| [ACCESS_CONTROL_MATRIX.md](ACCESS_CONTROL_MATRIX.md) | Role, domain, subject, and separation-of-duties boundaries. |
| [DATA_CLASSIFICATION.md](DATA_CLASSIFICATION.md) | Data classes, handling constraints, and prohibited logging. |
| [KEY_MANAGEMENT.md](KEY_MANAGEMENT.md) | Signing-key lifecycle and historical verification boundary. |
| [RETENTION_AND_DELETION.md](RETENTION_AND_DELETION.md) | Current retention controls and institutional decisions still required. |
| [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md) | Minimum operational response procedure. |
| [BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md) | Rehearsal evidence and recovery gates. |
| [PILOT_BOUNDARY.md](PILOT_BOUNDARY.md) | What a controlled pilot may and may not do. |

The test files named by the control register run in protected CI. Test output,
the pinned dependency inventory, container build, and PostgreSQL RLS rehearsal
are the repository-produced evidence. An institution must retain its own
deployment-specific evidence separately, without adding personal information,
tokens, or private keys to this repository.
