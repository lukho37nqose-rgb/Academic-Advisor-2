# Access And Trust

The Institutional Reasoning Engine must make institutional knowledge more legible without making a person's data, outcomes, or exceptional circumstances less safe.

## Access model

An approved domain may expose a public policy guide. It contains only the policy's human labels, conditions, values, release version, and source citations. It does not expose internal rule paths, unpublished drafts, personal evidence, extracted claims, facts, decision traces, or another person's outcome.

The guide is an explanation of an approved policy, not a self-service decision. A personalised evaluation still uses the deterministic evaluator, scoped evidence, a released rule graph, and the subject's authenticated institutional channel.

## When the policy does not fit

Every public guide can enable a human-assistance path. A person may identify missing information, a unique circumstance, an accessibility need, or another barrier without having to turn that message into machine evidence.

Support requests are stored in a separate workflow table. They cannot alter evidence, facts, policy drafts, releases, or a decision. An assigned staff member can view requests only for their domains and move a request through `OPEN`, `IN_PROGRESS`, and `CLOSED`. Each status transition is appended to a per-request sequence with the responsible account. Auditors can inspect the queue and its history but cannot alter it.

When an institution enables assistance for a new domain, it must record a privacy notice URL, a response target in hours, and an assisted or offline contact route. Every new request receives a response deadline. Closing a request starts its configured retention period; reopening it clears the expiry. Run `python -m app.services.retention` on the institution's scheduler at least daily to delete closed requests and their status history after the retention period.

Missing or disputed information must lead to `NEEDS_MANUAL_REVIEW`, not an automatic adverse conclusion. A human response must never silently modify a signed release or deterministic trace.

## Reviewing a personal decision

An institution may enable authenticated decision-review casework for a domain.
A person can open a case only against their own stored reasoning trace, identify
the facts they dispute, and cite new evidence already held in their institutional
record. The original evidence, accepted facts, signed release, decision trace,
and explanation remain intact. A later evaluation is a new trace, never an edit
to history.

Review cases use the constrained sequence `SUBMITTED`, `ACKNOWLEDGED`,
`UNDER_REVIEW`, `RESOLVED`, and `CLOSED`. Resolving a case requires both a
resolution category and a written institutional response. Each transition is
append-only with the responsible account. A coordinator can act only in an
assigned domain; a subject can see only their own cases. An institution must
configure a response target, privacy notice, assisted/offline route, and
retention period before enabling this casework.

## Accessibility requirements

For a production pilot, the institution must provide:

- A no-login public policy guide for each policy it chooses to publish.
- Source citations and release versions in plain language.
- A human channel for inaccessible information, exceptional cases, and questions the guide cannot answer.
- A documented response owner and service target for assistance requests.
- Accessible keyboard operation, labelled controls, status announcements, and responsive layouts in the public and staff interfaces.
- An equivalent assisted or offline route for people who cannot use the digital channel.

## Non-negotiable operational controls

- Public assistance submissions are limited per salted client fingerprint and domain. Production requires Redis and a non-default rate-limit salt.
- Publish the privacy notice and ensure the scheduled retention task runs successfully.
- Restrict staff access with institutional SSO, tenant claims, role claims, and domain assignments.
- Monitor unanswered and repeatedly reopened requests as a signal that the published policy is inaccessible or incomplete.
- Test policy guides with real subjects, accessibility practitioners, and staff who handle exceptional cases before asserting that access is equitable.

These controls preserve the key separation: a policy can be transparent and approachable without becoming mutable, unreviewed, or less auditable.
