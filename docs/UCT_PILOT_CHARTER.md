# UCT Case Study: Controlled Pilot Charter

## Status and boundary

This document frames a proposed University of Cape Town (UCT) case study. It
does not represent a UCT policy, contract, affiliation, endorsement, or
authorisation to process UCT information. No UCT rule, person, record, or
decision may enter the IRE until UCT supplies the authoritative source and the
relevant institutional owners approve the pilot.

The first deployment mode is **non-operative validation**. It may reproduce and
explain decisions for agreed test cases, but it must not create, alter,
recommend as final, or automatically communicate an outcome that affects a
student, staff member, applicant, or any other person. A human institutional
process remains the sole source of an operative decision.

## Pilot question

Can one bounded UCT decision be faithfully represented from authoritative,
versioned institutional material and explained back to the affected person with
the exact release and source citations that drove the result?

The pilot should select a single decision domain only after UCT's policy owner
has approved its scope. The choice must not be expanded through convenience or
feature pressure.

## Required UCT owners

UCT must name people, not just teams, for the following responsibilities before
any source or personal evidence is accepted:

| Responsibility | Required authority |
| --- | --- |
| Policy owner | Confirms the meaning, authoritative version, amendments, and effective dates of the selected rules. |
| Independent release approver | Approves or rejects a compiled policy release and is not its author. |
| System owner | Owns the system-of-record integration and operational change window. |
| Identity owner | Approves OIDC claims, access revocation, and staff role assignment. |
| Privacy and information-security lead | Approves the data categories, legal basis, retention, hosting, and incident path. |
| Accessibility and student-support lead | Approves the public explanation, assisted/offline route, and response commitment. |
| Appeals or casework owner | Defines how a person challenges missing evidence, source errors, or an exceptional circumstance. |

## Inputs UCT must provide

1. Authoritative source documents: issued handbook or policy PDFs, amendments,
   effective dates, superseded editions, and a named source of truth.
2. A policy interpretation record: scope, definitions, known ambiguities,
   exceptions, transitional provisions, and the outcome that remains subject to
   human discretion.
3. A privacy-approved, minimised test set of representative cases, including
   difficult, disputed, missing-information, and accessibility cases. Synthetic
   cases are preferred for the first end-to-end rehearsal.
4. A signed-off identity contract: issuer, audience, JWKS URL, stable subject
   identifier, tenant, role, domain claims, deprovisioning process, and break-
   glass controls.
5. A written retention schedule for source documents, evidence, reasoning
   traces, support requests, backups, logs, and exports.
6. A recovery and escalation contact list covering policy error, data incident,
   system outage, inaccessible communication, and appeal.

## Scope controls

The first case study may use only the approved domain, document corpus, user
roles, test population, and integration path. It must not:

- ingest records from an unapproved UCT system;
- use a model-produced extraction as a policy release without human review;
- infer facts a person cannot inspect or challenge;
- make an adverse decision automatically;
- replace an existing appeal, accommodation, or discretionary process;
- publish policy material that UCT has not approved for publication.

## Entry gates

Before non-operative evaluation begins, all of the following must be evidenced:

- UCT owners above have accepted their responsibilities in writing.
- The selected source corpus has immutable hashes, document metadata, page-level
  citations, an effective-period register, and documented resolutions for every
  policy ambiguity that could affect the pilot population.
- The policy owner and independent approver have passed a draft/review/release
  rehearsal using separate identities.
- The decision-review workflow has been rehearsed with a subject identity,
  correction evidence, a reasoned staff response, and a separate follow-up
  evaluation trace. The original trace must remain unchanged.
- The production configuration checks pass with managed Postgres, Redis, object
  storage, OIDC, a valid governance signing key, and reviewed migrations.
- Accessibility review confirms keyboard operation, understandable citations,
  accessible support contact, and an equivalent assisted/offline path.
- A security and privacy review accepts the threat model in
  [UCT_THREAT_MODEL.md](UCT_THREAT_MODEL.md), including any remaining risks.

## Exit and stop criteria

The pilot is ready to report results only when it reproduces an agreed sample
of known outcomes, retains the signed release and citations for every outcome,
and categorises every mismatch as a source, modelling, evidence, or governance
issue.

Stop validation processing and notify the named UCT owners when there is a
source integrity failure, cross-tenant or cross-subject access concern,
unauthorised release, incorrect or inaccessible explanation, missing assisted
route, or a security/privacy incident. Resume requires documented remediation
and a fresh approval by the appropriate UCT owner.

Moving from non-operative validation to any live decision support is a separate
governance decision. It requires a new scope approval, independent legal/privacy
and accessibility review, operational runbook rehearsal, and explicit agreement
on human accountability for every outcome.
