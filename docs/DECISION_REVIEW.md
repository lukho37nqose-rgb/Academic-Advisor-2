# Decision Review Cases

## Purpose

Decision review is an authenticated, subject-owned casework workflow for a
person who believes a stored decision trace contains missing or incorrect
information, needs a policy interpretation, has an exceptional circumstance,
or cannot use the explanation as presented. It is not an automated appeal
decision and it does not replace an institution's approved statutory,
academic, disciplinary, or accommodation process.

## Invariants

- A subject can submit a case only against their own tenant-scoped reasoning
  trace and may cite only evidence that belongs to that same subject and domain.
- Submitting or resolving a case never changes the source evidence, accepted
  facts, signed release, policy, original decision, or original explanation.
- A correction is assessed through a new evaluation and produces a new trace.
  Both traces remain available for audit.
- A coordinator is restricted to assigned domains. A subject sees only their
  own cases. Tenant administrators retain monitored break-glass access.
- Each action writes an append-only event with a sequence number and actor.

## Workflow

`SUBMITTED -> ACKNOWLEDGED -> UNDER_REVIEW -> RESOLVED -> CLOSED`

Only the next permitted state can be recorded. `RESOLVED` requires a resolution
category and a written institutional response. The available categories are
`DECISION_CONFIRMED`, `RE_EVALUATION_REQUIRED`,
`POLICY_CLARIFICATION_PROVIDED`, `EXCEPTION_REFERRED`, and `OUT_OF_SCOPE`.
The response is a human record, not a mutation of the deterministic outcome.

## Institutional configuration

An administrator enables casework through the no-code institutional intake. A
domain must declare `decision_review_enabled`, a decision-review response
target, privacy notice, and an assisted/offline route. The runtime rejects a
submission when those commitments are absent.

Closed cases are retained for `DECISION_REVIEW_RETENTION_DAYS`, which defaults
to 365 days and is checked by `python -m app.services.retention`. The pilot
institution must set its own approved retention period before processing real
records.

## Subject review surface

The reference frontend exposes a separate trace-bound subject surface at
`/?experience=subject&trace={reasoning_graph_id}`. The API, not this route,
enforces that the authenticated subject owns the trace. The surface records a
category, an explanation, and optionally the displayed facts that need checking;
it does not expose raw evidence identifiers or allow the original trace to be
edited.

An institutional portal should link to this surface from an authenticated list
of that person's decisions. The route is a reference integration boundary, not
an assertion that a URL alone constitutes subject authentication.

## UCT pilot use

For the UCT case study, this workflow must remain in shadow mode until UCT has
approved its policy owner, casework owner, privacy basis, response commitment,
assisted route, and the relationship to any existing UCT review or appeal
process. A case outcome must not be communicated as an operative UCT decision
until that separate approval exists.
