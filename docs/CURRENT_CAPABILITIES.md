# Current Capabilities

This is a precise description of what the application can do today. It is not
a promise that the system is ready to make decisions for UCT or any other
institution without the deployment and pilot controls described below.

## In plain language

An institution can put a policy into a controlled draft, have a different
person approve it, and then use the approved version to produce the same
decision every time from the same evidence. The decision has a trace showing
which rule and which facts led to it. That trace is tied to the exact signed
policy version used at the time.

The application can also accept a handbook PDF as a source document, keep a
hash of the source, extract bounded page excerpts, and present OCR text as a
human-reviewed proposal. A PDF or OCR result never changes a policy by itself.

It has a small, controlled way to correct approved display metadata, such as a
course description. Those corrections are limited to fields an institution has
configured as low risk and receive an audit record. They cannot alter a rule,
prerequisite, credit requirement, or published release.

The system can define and independently approve a CSV mapping for a
system-of-record export, then check a file against that mapping. It does not
import the CSV into institutional records or write back to any external system.

People governed by a decision can view an approved public policy guide, open a
human-assistance request where enabled, and request a review of their own
decision trace. Those workflows do not change the original evidence, facts, or
policy release.

## What each account can see

The reference client calls `GET /api/v1/session/capabilities` after sign-in.
The server returns only the approved workspace routing information, not a
subject identifier, user identifier, or domain assignments. The client hides
all other pages, and every API route independently repeats the server-side
role, tenant, domain, and subject-ownership check.

| Account role | Visible workspace pages | Actions it may take |
| --- | --- | --- |
| Subject | Public policy guide; their own trace link | View their own trace; request assistance or a review where the institution enabled it. |
| Metadata steward | Governance Desk | Apply only pre-configured low-risk metadata edits in assigned domains. |
| Assistance coordinator | Assistance Inbox; Review Cases | Triage assistance and decision-review case statuses in assigned domains. |
| Policy author | Handbook Intake; System Records; Policy Register | Upload/review source material, submit mapping configurations, record policy ambiguities, and use the draft API. Cannot approve releases. |
| Release approver | Handbook Intake; System Records; Policy Review; Policy Register | Inspect source material, independently review mappings, inspect ambiguities, and approve a release. Cannot upload or revise a handbook source. |
| Policy owner | Policy Register | Record or resolve documented interpretations with an authoritative source. A person cannot resolve their own ambiguity record. |
| Auditor | Governance Desk; Handbook Intake; System Records; Assistance Inbox; Policy Review; Policy Register | Read-only inspection of configured controls, source material, mapping records, casework, policy review, and interpretation records. |
| Tenant administrator | All staff pages | Break-glass administration across the tenant. The release and mapping workflows still enforce separation of duties. |

The former demo `Begin Investigation` control is deliberately not presented in
the tenant workspace. An evaluation can create decision artefacts and audit
activity, so the production UI must not create one from placeholder data. The
evaluation API remains limited to a tenant administrator or the subject who
owns the evidence; a real operational evaluation flow is still to be built.

## Controls that are implemented

- Deterministic evaluation of compiled policy rules. AI may help at extraction
  or explanation boundaries, but it does not decide the outcome.
- Policy drafts are compiled before storage, approved by a different identity,
  released immutably, cryptographically signed, and versioned with effective
  dates and applicability selectors.
- Tenant, domain, and subject binding is checked in the API. Production
  PostgreSQL uses transaction-scoped tenant context and row-level security.
- Handbooks are stored as private, hashed sources. Large PDFs are reviewed in
  bounded page batches; their worker checkpoints allow a long document to
  resume rather than be handled as one browser request.
- OCR output is untrusted until a permitted human accepts, corrects, or rejects
  it. It is not automatically converted into a rule or release.
- System-record mapping configuration is immutable after submission, has an
  append-only event history, and requires an independent reviewer before it is
  approved.
- Public assistance has rate limiting, retention fields, and an offline or
  assisted-route configuration. Decision-review cases are subject-owned and
  append their lifecycle history.
- Production startup fails closed without OIDC/JWKS, Postgres, Redis, object
  storage, signing material, reviewed migrations, and explicit browser/host
  allow-lists.

## What it does not do yet

- It has not been verified against UCT's real handbook corpus, policies,
  student records, or governance process.
- It has no completed institutional SSO browser flow; the reference client
  accepts a host-supplied bearer token while the API validates the token.
- It has no operational administrator interface for authoring every kind of
  policy draft, no completed student evidence/appeal portal, and no production
  notification service.
- It does not perform a live system-of-record import, automated handbook-to-
  rule conversion, or external workflow write-back.
- It does not substitute for institutional policy interpretation, legal review,
  accessibility review, retention approval, or a named human decision owner.
- Recovery drills, monitoring, backup restoration, penetration testing, and
  real serving/migration database-role rehearsals must still be performed with
  the institution before production use.

## Safety boundary

Seeing a page is not permission to make a change. The browser hides actions to
reduce mistakes and unnecessary case or audit activity. The API and database
remain the enforcement boundary: a modified browser, copied URL, or direct API
request must still satisfy the same role, tenant, domain, separation-of-duties,
and subject-ownership checks.
