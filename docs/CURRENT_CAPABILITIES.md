# Current Capabilities

This is a precise description of what the application can do today. It is not
a promise that the system is ready to make decisions for UCT or any other
institution without the deployment and pilot controls described below.

## In plain language

An institution can put a policy into a controlled draft, have a different
person approve it, then evaluate accepted facts against that
approved version. The same accepted facts and policy release produce the same
decision every time. A decision has a trace showing which rule and facts led to
it, and is tied to the exact signed policy version used at the time.

Raw evidence does not decide anything. An authorised staff member records a
candidate fact against preserved source bytes, a quotation, and a location. A
different approver or tenant administrator accepts or rejects it. Confirmed
records from an independently approved system-of-record mapping are accepted
through that recorded mapping review. Before a
decision or replay is run, the application recalculates the SHA-256 hash of the
stored source and fails closed if it no longer matches the evidence record.

The application can also accept a handbook PDF as a source document, keep a
hash of the source, extract bounded page excerpts, and present OCR text as a
human-reviewed proposal. A PDF or OCR result never changes a policy by itself.

It has a small, controlled way to correct approved display metadata, such as a
course description. Those corrections are limited to fields an institution has
configured as low risk and receive an audit record. They cannot alter a rule,
prerequisite, credit requirement, or published release.

The system can define and independently approve a source-record mapping, then
check a file-based export against that mapping. CSV remains the portable
fallback and regression fixture; the enterprise path is governed read-only
source-system access that creates evidence and accepted facts only after source
and mapping review. It does not write back to any external system.

Staff can also create an outcome-calibration suite without writing code or JSON.
It compares synthetic representative cases, or privacy-approved de-identified
historical cases, with one signed policy release. A different staff member must
certify the suite before it can run. The comparison produces an immutable report
of matches and mismatches; it cannot alter a subject record, a policy release,
or an operative institutional decision.

An assigned staff member can record an already-authorised concession,
appeal outcome, curriculum applicability decision, assessment accommodation, or
other structured context event. A different approver or tenant administrator
must certify it before a subject can see a safe explanation in their
Institutional Timeline. Later events can supersede or revoke earlier ones
without erasing the original record.

People governed by a decision can view an approved public policy guide, open a
human-assistance request where enabled, and request a review of their own
decision trace. Their trace view presents the current policy position, the
conditions and facts that produced it, the policy release used, whether human
consideration is required, and the available review route. Where a release
contains structured policy-source pointers, the subject view explains the
condition first and then points to the authoritative source title, version,
page range, section, and safe source anchor retained with the historical trace.
Those workflows do not change the original evidence, facts, or policy release.

## What each account can see

The reference client calls `GET /api/v1/session/capabilities` after sign-in.
The server returns only the approved workspace routing information, not a
subject identifier, user identifier, or domain assignments. The client hides
all other pages, and every API route independently repeats the server-side
role, tenant, domain, and subject-ownership check.

| Account role | Visible workspace pages | Actions it may take |
| --- | --- | --- |
| Subject | Public policy guide; their own personal policy-position view | View how the common approved policy applies to their own authorised trace; request assistance or a review where the institution enabled it. |
| Staff member | Governance Desk; Assistance Inbox; Review Cases; Institutional Timeline; Evidence Facts | Work with assigned-domain records and casework, ingest authorised evidence, propose cited facts, record institutional context, and apply pre-configured low-risk metadata edits. Cannot attest their own work or change policy. |
| Policy editor | Institution Setup; Handbook Intake; System Records; Policy Register; Outcome Calibration | Build no-code domains and policy drafts, upload/review source material, submit mappings, record ambiguities, and prepare non-identifying calibration suites. Cannot approve releases or certify their own calibration suite. |
| Approver | Handbook Intake; System Records; Policy Review; Policy Register; Outcome Calibration; Institutional Timeline; Evidence Facts | Independently accept or reject cited facts and context, settle sourced interpretations, review mappings and calibration cases, and publish another person's release. A person cannot approve their own work. |
| Auditor | Governance Desk; Handbook Intake; System Records; Assistance Inbox; Policy Review; Policy Register; Outcome Calibration; Institutional Timeline; Evidence Facts | Read-only inspection of configured controls, source material, mapping records, casework, policy review, interpretation records, calibration reports, and evidence-fact history. |
| Tenant administrator | All staff pages | Break-glass administration across the tenant. The release and mapping workflows still enforce separation of duties. |

The former reference `Begin Investigation` control is deliberately not presented in
the tenant workspace. An evaluation can create decision artefacts and audit
activity, so the production UI must not create one from placeholder data. The
evaluation API remains limited to a tenant administrator or the subject who
owns the evidence; a real operational evaluation flow is still to be built.

## Controls that are implemented

- Deterministic evaluation and trace-bound explanation of compiled policy rules.
  Evaluation accepts only governed, accepted facts bound to preserved source
  bytes. Automated extraction remains untrusted source assistance, not policy
  logic or an outcome decision.
- Auditors can run a replay verifier. It rechecks the evidence hash, signed
  release bundle, accepted-fact lineage, and recomputed trace rather than merely
  returning the earlier trace. PostgreSQL makes decision-bearing evidence,
  claims, facts, traces, releases, and compiled rules append-only.
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
- Releases bind their cited rule-source manifest into the signed release
  payload. Rules may also carry structured policy-source pointers with stable
  source identifiers, versions, document hashes, page ranges, sections, rule
  identifiers, and safe anchors where the governed source artifact supports
  them. A production evaluation fails closed if release metadata, policy,
  source manifest, compiled graph, or signature no longer agree.
- Outcome-calibration suites are tenant and domain scoped, immutable after
  submission, independently certified, and recorded as a single immutable
  non-operative run. The author cannot certify their own suite or classify its
  mismatches.
- Institutional context events require an authority and source decision
  reference, remain immutable after submission, and have an append-only
  independent certification trail. Subject views exclude staff-only events and
  internal references.
- Public assistance has rate limiting, retention fields, and an offline or
  assisted-route configuration. Decision-review cases are subject-owned and
  append their lifecycle history.
- Production startup fails closed without OIDC/JWKS, Postgres, Redis, object
  storage, signing material, reviewed migrations, and explicit browser/host
  allow-lists.

## What it does not do yet

- It has not been verified against UCT's real handbook corpus, policies,
  student records, or governance process.
- It has an institutional OIDC browser flow in the reference client, and the
  API validates the token. A real deployment still requires the institution's
  approved IdP registration, claim mapping, revocation rehearsal, and portal or
  hosting route.
- It has no operational administrator interface for authoring every kind of
  policy draft, no completed subject evidence/appeal portal, and no production
  notification service.
- An accepted evidence fact cannot be overwritten. Corrections use a successor-
  fact relationship that preserves the original evaluation input and records an
  append-only supersession event.
- It does not yet include a production-approved live system-of-record connector,
  automated handbook-to-rule conversion, or external workflow write-back.
- It does not automatically ingest transcripts, committee decisions, emails, or
  historic records into the Institutional Timeline. Staff must first record and
  certify context with institution-approved source references.
- Certified context is not yet an evaluator input. It explains history but does
  not automatically grant an exception or change an operative decision.
- It does not detect all personal information entered by a staff member. Its
  calibration route therefore accepts only non-identifying case references and
  requires institutional privacy approval before de-identified historical data
  is used.
- It does not substitute for institutional policy interpretation, legal review,
  accessibility review, retention approval, or a named human decision owner.
- Recovery drills, monitoring, backup restoration, penetration testing, and
  real serving/migration database-role rehearsals must still be performed with
  the institution before production use.
- Object-store write-once retention, versioning, and restoration must be
  configured and tested by the deploying institution. The application detects a
  changed source hash; it does not itself configure an institution's bucket
  retention policy.

## Safety boundary

Seeing a page is not permission to make a change. The browser hides actions to
reduce mistakes and unnecessary case or audit activity. The API and database
remain the enforcement boundary: a modified browser, copied URL, or direct API
request must still satisfy the same role, tenant, domain, separation-of-duties,
and subject-ownership checks.
