# Institutional Timeline

The Institutional Timeline preserves certified institutional context from a
subject's perspective. It answers how a current position developed without
creating a private policy or rewriting the historical record.

## Scope

The first implementation records subject-specific institutional context such as
concessions, curriculum applicability, assessment accommodations, appeal
outcomes, registration positions, progression positions, and graduation
positions. It can link an event to the signed policy release and citation that
made the context relevant.

It is not a transcript, an evidence store, a free-form notes system, or an
automated policy exception service.

## Governed Lifecycle

1. A staff member records an already-authorised decision with
   an authority reference and source decision reference.
2. The event is immutable from submission onward and is not visible to the
   subject yet.
3. A different approver or tenant administrator certifies or rejects the
   record. The person who recorded it cannot attest it.
4. Certified subject-safe events appear in the subject timeline. Staff-only
   records remain unavailable to the subject.
5. A later certified event can supersede or revoke an earlier event. Both remain
   in the historical sequence; the timeline derives their current state rather
   than overwriting the original decision.

Every submission and certification has an append-only attestation record. In
PostgreSQL, row-level security, immutable-input triggers, lifecycle triggers,
and append-only attestation triggers protect the database boundary.

## Subject Privacy

The subject view exposes only the certified explanation, institutional effect,
named authority, effective period, and relevant policy release or citation. It
does not expose internal source references, staff identities, attestation notes,
or supporting evidence.

The person recording an event is responsible for making its subject-safe
explanation free of medical detail, third-party data, and other information the
institution should not disclose. The application cannot reliably infer every
sensitive detail in free text, so institutional privacy guidance and review are
still required.

## Evaluation Boundary

Institutional context is **not yet an evaluator input**. The current release
records and explains it, but it does not automatically grant an exception,
alter a fact, or change an operative decision.

Before a policy release may consume a context event, the policy model must name
the specific context type and the authorised effect it accepts. That later work
must retain the same signed-release, temporal-applicability, separation-of-
duties, and trace requirements as the rest of the decision engine.

## Institution Neutrality

UCT is a possible first case study, not a schema, tenant, policy source, or
identity assumption. Each institution supplies its own authorities, source
references, privacy rules, decision categories, and access assignments.
