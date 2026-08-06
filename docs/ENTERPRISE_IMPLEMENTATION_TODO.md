# Enterprise Implementation TODO

This TODO moves the Institutional Reasoning Engine from the current reference
implementation into a full-stack enterprise implementation for a controlled
institutional pilot. It assumes two product decisions:

1. Do not build a local mock identity provider as the product path. Use full
   enterprise SSO with the institution's identity provider.
2. Do not stop at a CSV-only system-of-record boundary. Build read-only
   institutional connectors so IT does not have to create a bespoke CSV export
   before a pilot can begin.

The target posture is an institution-controlled, production-style deployment
with real SSO, governed read-only source-system access, audited policy and fact
lifecycles, and clear pre-production validation language.

## 0. Current Baseline To Preserve

- [x] Keep the deterministic evaluator domain-neutral.
- [x] Keep signed, immutable policy releases with release-bundle verification.
- [x] Keep independent author and approver controls for facts, mappings,
  ambiguities, context, and releases.
- [x] Keep evidence and source hashing before evaluation and replay.
- [x] Keep tenant, domain, role, and subject ownership checks in the API.
- [x] Keep PostgreSQL RLS as a production deployment gate.
- [x] Keep OCR and external AI output outside the decision path until a human
  reviewer accepts a cited fact or policy draft change.
- [x] Keep external workflow delivery fail-closed until a durable dispatcher,
  credentials, reconciliation, and incident route are approved.
- [x] Keep frontend build, lint, and backend test checks as required release
  gates.

## 1. Product Language And Positioning

- [x] Replace user-facing "demo" wording with "reference", "sample",
  "pre-production", or "validation" depending on context.
- [x] Replace user-facing "shadow pilot" wording with "controlled
  pre-production validation" unless the phrase is being used as a precise
  audit term.
- [x] Rename visible "shadow calibration" labels to "outcome calibration" or
  "pre-production calibration".
- [x] Keep "synthetic" for test data and fixtures, but make clear that
  synthetic fixtures are engineering controls, not the enterprise pilot path.
- [x] Audit docs and UI for `demo`, `mock`, `shadow`, `sandbox`, and
  `sample`; decide case by case whether each term is public-facing,
  developer-only, or obsolete.
- [ ] Rename `demo_university` and `demo_foundation` tenant examples to
  `sample_university` and `sample_foundation`, including tests, docs, and Edge
  fixture paths.
- [ ] Update the README "Current State" and "Production Risks" sections so the
  narrative says: enterprise SSO and institutional connectors are planned
  implementation work, not optional future nice-to-haves.
- [x] Add a product boundary statement: IRE integrates with institutional
  systems for governed read-only evidence/fact sourcing, but it does not
  replace the source system or write back without a separately approved
  workflow.
- [ ] Add a release note explaining the language change so reviewers understand
  that safety boundaries remain intact.

## 2. Enterprise Discovery And Pilot Contract

- [ ] Select one first enterprise pilot institution and one bounded decision
  domain.
- [ ] Name the institutional system owner, policy owner, privacy contact,
  identity owner, source-system owner, records owner, support owner, and
  incident contact.
- [ ] Record the pilot success definition in a signed pilot charter.
- [ ] Record exactly which decision is in scope and which decisions are out of
  scope.
- [ ] Record the data categories required for the decision and the minimum fact
  set needed by the evaluator.
- [ ] Record whether the first validation uses de-identified historical cases,
  institution-approved synthetic representatives, or production-adjacent
  staging records.
- [ ] Record the expected user groups: subjects, staff members, policy editors,
  approvers, auditors, tenant administrators, and system service identities.
- [ ] Record the allowed deployment surfaces: institution portal, direct app
  URL, provider operations surface, API-only integration, or embedded route.
- [ ] Record the non-negotiable safety constraints: no unmanaged passwords, no
  broad tenant administrator accounts, no write-back to source systems, no
  evidence in logs, no source-system secrets in Git or browser code.
- [ ] Convert the charter into acceptance criteria before implementation
  starts.

## 3. Full-Stack SSO Architecture

- [ ] Choose the first supported IdP integration path. Prefer Microsoft Entra ID
  for the first enterprise implementation if the institution uses it; otherwise
  use the institution's OIDC-compatible provider.
- [ ] Decide whether SSO configuration is global per deployment or tenant-scoped
  in the database. For multi-tenant provider operations, implement
  tenant-scoped IdP configuration.
- [ ] Add a tenant IdP configuration model if tenant-scoped SSO is required:
  issuer, discovery URL, JWKS URL, audience, allowed algorithms, claim mapping,
  logout URL, status, author, reviewer, timestamps, and audit events.
- [ ] Add an approval workflow for tenant IdP configuration. A tenant
  administrator should submit it, and a separate authorised reviewer should
  approve it before production traffic uses it.
- [ ] Implement OIDC discovery support from the issuer's
  `.well-known/openid-configuration`.
- [ ] Implement JWKS caching with expiry, `kid` miss refresh, issuer pinning,
  audience validation, algorithm allow-listing, expiration validation, and
  clock-skew handling.
- [x] Keep HS256 development token support unavailable in production.
- [ ] Add fail-closed startup checks for tenant-scoped IdP configuration if the
  deployment expects tenant-managed SSO records.
- [x] Define a stable claim contract: subject identifier, tenant, role, domain
  assignments, display name where allowed, and email only if the institution
  approves it for support workflows.
- [ ] Implement group-to-IRE-role mapping if the institution cannot emit the
  IRE role claim directly.
- [ ] Implement domain assignment mapping from IdP groups or claims to IRE
  domain IDs.
- [x] Add strict validation for missing, blank, duplicate, unknown, or
  cross-tenant domain assignments.
- [ ] Add role downgrade and account removal tests. A removed role must lose
  access on the next token refresh or introspection boundary agreed with the
  institution.
- [ ] Add an explicit service identity model for scheduled connector jobs.
  Service identities must be non-human, least-privilege, tenant-scoped, and
  audited.
- [ ] Decide whether SCIM provisioning is required for phase one. If required,
  add SCIM user and group ingestion as a governed identity input, not as a
  password store.

## 4. Frontend SSO Implementation

- [x] Choose the frontend OIDC client library and add it through the normal
  dependency review process.
- [x] Implement authorization-code-with-PKCE login.
- [x] Implement callback handling without exposing client secrets.
- [ ] Implement silent token renewal or a clear session expiry path according
  to the institution's IdP policy.
- [x] Implement logout and IdP session termination where supported.
- [ ] Store tokens only in the approved browser storage model for the selected
  OIDC library and institution risk decision.
- [ ] Remove any product-facing bearer-token paste or manual token path from the
  enterprise surface.
- [x] Keep `/api/v1/session/capabilities` as the only frontend source of visible
  pages and actions.
- [x] Add loading, expired-session, access-denied, role-removed, and
  IdP-unavailable states.
- [ ] Add provider-operations routing for tenant administrators who manage
  enterprise setup.
- [ ] Add Playwright coverage for login, callback, role-specific routes,
  logout, expired token, and direct URL denial using an approved staging IdP
  client.
- [x] Document how an institution portal can launch the app without the browser
  inventing roles or domain assignments.

## 5. API Identity Enforcement

- [x] Centralise identity parsing so every route receives the same validated
  identity object.
- [ ] Add tenant-scoped IdP lookup if multiple institutions share the provider
  deployment.
- [x] Add tests for wrong issuer, wrong audience, expired token, unknown role,
  unknown tenant, missing domain, duplicate domains, subject without subject
  identifier, and staff token with an irrelevant subject identifier.
- [ ] Add audit events for access-denied cases that are useful for security
  review without logging token contents or personal evidence.
- [ ] Add request correlation between ingress, API, worker, and connector jobs.
- [ ] Add rate limits for login-adjacent public routes and support endpoints.
- [x] Add documentation for IdP key rotation and token revocation rehearsal.
- [ ] Add a runbook for an IdP outage, including which routes should fail closed
  and what human assistance path remains available.

## 6. Enterprise Tenant Setup Workflow

- [ ] Build a tenant setup checklist in the provider/admin surface.
- [ ] Add tenant lifecycle states: onboarding, configuration review,
  pre-production validation, active pilot, suspended, and decommissioning.
- [ ] Add setup status for identity, source systems, policy domain, evidence
  retention, object storage, RLS rehearsal, monitoring, support route, and
  incident route.
- [ ] Add tenant setup APIs that expose status only to provider operators and
  tenant administrators.
- [ ] Add immutable setup audit events for each checklist state change.
- [ ] Add a tenant readiness endpoint that explains blockers without exposing
  secrets.
- [ ] Add docs for institution responsibilities and provider responsibilities.
- [ ] Add a deployment gate that prevents active pilot status until required
  setup items are complete.

## 7. Read-Only System-Of-Record Connector Strategy

- [x] Keep the safety principle: IRE reads authorised data to create governed
  evidence and facts; it does not become the source of record.
- [x] Replace "CSV required" as the enterprise path with "CSV remains a fallback
  and test fixture; read-only connectors are the preferred pilot path."
- [ ] Define the first connector type with the pilot institution. Candidate
  types: REST API, SFTP managed export pull, database read-only view, or
  vendor-specific API.
- [ ] For each connector type, document the minimum permissions, network route,
  service identity, secret storage, rate limits, data classification, and
  incident owner.
- [ ] Add a connector interface in the backend: discover schema, test
  connection, fetch sample records, run extraction, produce reconciliation
  preview, and materialise approved facts.
- [x] Add connector configuration records: tenant, domain, source system,
  connector kind, credential reference, endpoint reference, allowed object,
  status, author, reviewer, timestamps, and audit events.
- [x] Store connector secrets only in the institution-approved secrets manager.
  Database records should hold secret references, never secret values.
- [x] Require independent approval before a connector can fetch subject-bearing
  records.
- [ ] Add a network allow-list or private connectivity requirement for
  enterprise deployments.
- [ ] Add connector health checks that verify metadata access without fetching
  personal records.

## 8. Connector Data Model And Migrations

- [x] Extend institutional data-source tables to represent live connector
  configuration, not only descriptive source records.
- [ ] Add connector status history: submitted, test_failed, approved,
  enabled, paused, retired, and failed.
- [ ] Add connector run tables: run ID, tenant, domain, connector, started by,
  service identity, status, started at, ended at, source watermark, record
  counts, hashes, and safe error classification.
- [ ] Add connector reconciliation tables that store counts and digests, not raw
  subject values.
- [ ] Add source-record lineage fields to materialised facts so every accepted
  fact can be traced to connector, run, source record version, mapping review,
  and source as-of date.
- [ ] Add idempotency keys for connector runs and per-record materialisation.
- [ ] Add retention fields for connector run metadata.
- [ ] Add PostgreSQL RLS policies for connector configuration, connector runs,
  reconciliation reports, and source lineage records.
- [ ] Add append-only protections for connector audit and run history.
- [ ] Add Alembic migrations and downgrade notes for every schema change.

## 9. Connector Mapping And Review UX

- [x] Upgrade the System Records screen from CSV-only mapping to
  connector-backed source discovery.
- [x] Let an authorised editor choose an approved source system and connector.
- [ ] Let the UI fetch source schema, field labels, types, and sample-safe
  metadata without displaying unnecessary subject values.
- [ ] Let the editor map source fields to declared domain facts.
- [ ] Display requiredness, type conversion, source as-of semantics, and
  subject identifier matching rules.
- [ ] Validate mappings in the browser for usability and again in the API for
  enforcement.
- [x] Submit mappings as immutable pending records.
- [x] Add independent review screens for mappings, connector access, and
  source authority.
- [x] Prevent authors from approving their own connector or mapping.
- [ ] Show a safe preview report: counts, type failures, missing fields,
  duplicate source identifiers, changed records, removed records, and blocked
  rows without exposing subject values broadly.
- [ ] Add a user-facing distinction between confirmed authoritative records and
  provisional working records.
- [ ] Add clear failure states for unavailable source system, expired service
  credential, mapping drift, and schema drift.

## 10. Connector Runtime

- [ ] Implement a durable connector job queue using the existing background job
  patterns.
- [ ] Add per-tenant worker allow-lists for connector jobs.
- [ ] Add connector run leasing, retries, dead-letter handling, and manual
  retry approval.
- [ ] Add source-system rate limiting and backoff.
- [ ] Add timeouts for schema discovery, preview, extraction, and
  materialisation.
- [ ] Add source watermarks or version cursors where the source system supports
  them.
- [ ] Add all-or-nothing preview validation before facts are materialised.
- [ ] Add reconciliation approval when a run adds, changes, or removes records
  compared with the prior accepted snapshot.
- [ ] Add a materialisation step that creates evidence and accepted facts only
  through an independently approved connector mapping.
- [ ] Preserve raw source bytes or canonical source payload hashes according to
  the institution's retention decision.
- [ ] Ensure connector errors do not log subject identifiers, source values,
  credentials, query strings, or full payloads.
- [ ] Add connector metrics: run duration, records processed, rows blocked,
  schema drift, credential failures, rate-limit events, and dead letters.
- [ ] Add alerts for repeated connector failures, stale source watermarks, and
  unexpected record-count changes.

## 11. First Connector Implementation

- [ ] Select the first real source-system connector with the institution.
- [ ] Obtain a staging or pre-production source-system endpoint.
- [ ] Create a least-privilege read-only service account.
- [ ] Store credentials or workload identity references in the secrets manager.
- [ ] Implement schema discovery for the selected source.
- [ ] Implement connectivity tests that prove the service account can read only
  the approved object or API scope.
- [ ] Implement extraction into the connector-neutral preview format.
- [ ] Implement source-record version and as-of date capture.
- [ ] Implement subject identifier matching to the SSO subject claim.
- [ ] Implement mapping drift detection.
- [ ] Implement contract tests against the institution's staging source.
- [ ] Implement failure-mode tests for permission denied, expired credential,
  source outage, schema drift, duplicate subject identifier, malformed value,
  and rate limit.
- [ ] Document the exact source scopes and permissions granted.
- [ ] Document how the institution can pause or revoke connector access.

## 12. Policy And Handbook Enterprise Flow

- [ ] Keep handbook upload as source intake, not automatic policy creation.
- [ ] Ensure large handbook sources use durable background workers and page
  checkpoints.
- [ ] Add frontend polling for source ingestion status if it is not complete.
- [ ] Add page-level review with source hash, page number, extraction kind,
  review priority, and reviewer decision.
- [ ] Add OCR provider configuration as tenant-scoped and independently
  reviewed if production OCR is enabled.
- [ ] Add OCR quality signals to the reviewer UI.
- [ ] Add table and structured block review where the selected handbook corpus
  requires it.
- [ ] Add rule-draft assistance only as a pending proposal requiring human
  policy-editor review and separate approval.
- [ ] Add provenance from every drafted condition back to source edition,
  section, page, quote, and reviewer decision.
- [ ] Add tests for large source resumability, OCR rejection, citation
  correction, policy change, and unsupported extraction output.

## 13. Decision And Review Flow For Enterprise Users

- [ ] Build the operational evaluation flow that starts from an approved policy
  release and accepted authoritative facts, not placeholder data.
- [ ] Add a staff workflow for evaluating a selected subject or cohort where
  permitted by the institution.
- [ ] Add subject-facing evidence visibility controls agreed with the
  institution.
- [ ] Add a complete subject evidence correction or challenge path.
- [ ] Add decision-review escalation and SLA routing by responsible group.
- [ ] Add case assignment, transfer, closure, retention, and export controls.
- [ ] Add auditor views for a full decision packet: source lineage, accepted
  facts, release bundle, trace, explanation, review cases, and replay result.
- [ ] Add "why this is not automatic final action" messaging for any decision
  that still requires human confirmation.
- [ ] Add accessibility review for subject-facing explanations and forms.

## 14. Infrastructure And Deployment

- [ ] Decide hosting model: institution-owned cloud account, provider-managed
  isolated tenant, or hybrid.
- [ ] Finalise Terraform for the selected hosting model.
- [ ] Provision Postgres, Redis, private object storage, secrets manager, TLS
  ingress, logging, metrics, alerts, backup storage, and container runtime.
- [ ] Configure remote encrypted Terraform state.
- [ ] Separate migration, serving, worker, connector, and break-glass
  identities.
- [ ] Ensure the serving database role is not superuser, not `BYPASSRLS`, and
  cannot create databases or roles.
- [ ] Configure private object storage versioning, lifecycle rules, encryption,
  and Object Lock or equivalent write-once retention where approved.
- [ ] Configure private network access to the source system where required.
- [ ] Configure WAF or ingress controls according to institutional policy.
- [ ] Configure central log redaction and retention before traffic.
- [ ] Configure backup and restore jobs.
- [ ] Configure monitoring for API, worker, connector, Redis, database,
  object-store errors, and IdP/JWKS failures.
- [ ] Build API and worker containers from pinned dependencies and a reviewed
  commit.
- [ ] Deploy migrations separately from application startup.
- [ ] Deploy the frontend with only approved public configuration.

## 15. CI/CD And Verification Gates

- [ ] Keep `python -m pytest -q` passing.
- [ ] Keep `python -m mypy --explicit-package-bases app` passing.
- [ ] Keep frontend lint passing.
- [ ] Keep frontend build passing.
- [ ] Add Playwright enterprise SSO route coverage.
- [ ] Add connector contract tests for the first source connector.
- [ ] Add migration verification for connector and IdP tables.
- [ ] Add dependency lock and SBOM verification to protected CI.
- [ ] Add container build verification with pinned base image digests.
- [ ] Add PostgreSQL RLS rehearsal in CI or controlled deployment workflow.
- [ ] Add Terraform validation and plan capture.
- [ ] Add security scanning according to institutional requirements.
- [ ] Require protected checks before deployment.

## 16. Security, Privacy, And Governance Gates

- [ ] Complete threat-model review for SSO, connector jobs, source-system
  access, subject-facing views, and admin operations.
- [ ] Complete data protection impact assessment or equivalent privacy review.
- [ ] Approve data minimisation for each source field used by the connector.
- [ ] Approve retention for evidence, source payload hashes, connector run
  metadata, support cases, review cases, logs, and backups.
- [ ] Approve legal hold and deletion authority.
- [ ] Approve support and offline assistance commitments.
- [ ] Approve accessibility testing plan and subject-facing content review.
- [ ] Run penetration or vulnerability testing against staging.
- [ ] Run IdP revocation rehearsal.
- [ ] Run connector credential revocation rehearsal.
- [ ] Run source-system outage rehearsal.
- [ ] Run backup restoration rehearsal.
- [ ] Run signing-key rotation rehearsal.
- [ ] Run incident escalation rehearsal.
- [ ] Record sign-off from policy, identity, source-system, privacy, security,
  support, and operations owners.

## 17. Pre-Production Validation

- [ ] Deploy a staging tenant with enterprise SSO enabled.
- [ ] Connect to the institution-approved staging or read-only source-system
  environment.
- [ ] Configure one bounded decision domain.
- [ ] Upload and review the approved policy corpus.
- [ ] Author and approve the first policy release.
- [ ] Configure and approve the first system-of-record connector.
- [ ] Configure and approve the source-to-fact mapping.
- [ ] Run source discovery and preview.
- [ ] Resolve mapping errors and schema drift.
- [ ] Materialise accepted facts from the approved connector mapping.
- [ ] Evaluate the approved validation cases.
- [ ] Compare outcomes with known institutional outcomes or approved expected
  results.
- [ ] Classify mismatches as source-data issue, policy-model issue, governance
  interpretation, or product defect.
- [ ] Fix defects and repeat validation until exit criteria are met.
- [ ] Produce a validation report with decision packets, replay results,
  mismatch classifications, and sign-offs.

## 18. Enterprise Pilot Launch

- [ ] Freeze the reviewed release commit.
- [ ] Confirm all protected checks pass.
- [ ] Confirm migrations have been applied by the migration principal.
- [ ] Confirm production startup checks pass.
- [ ] Confirm RLS rehearsal passes with serving and migration roles.
- [ ] Confirm SSO login works for every approved role.
- [ ] Confirm role removal and disabled account access fail closed.
- [ ] Confirm connector run succeeds from the approved source.
- [ ] Confirm connector pause and credential revocation work.
- [ ] Confirm support and review routes are staffed.
- [ ] Confirm monitoring and alerts reach the named owners.
- [ ] Confirm backup restore evidence is recorded.
- [ ] Confirm incident route and privacy contact are live.
- [ ] Enable the approved pilot tenant.
- [ ] Keep source-system write-back disabled unless a separate approved
  workflow dispatcher has been implemented and signed off.
- [ ] Monitor first-run connector results, evaluations, support cases, review
  cases, authorization denials, and worker backlog daily during launch.

## 19. Post-Launch Hardening

- [ ] Review access assignments after the first launch window.
- [ ] Review connector run history and unexpected changes.
- [ ] Review support and decision-review SLA performance.
- [ ] Review false denials, false approvals, and manual-review rates.
- [ ] Review policy ambiguity records and unresolved interpretations.
- [ ] Review OCR and handbook extraction backlog.
- [ ] Review replay verification results.
- [ ] Review incidents, near misses, and denied access patterns.
- [ ] Add the next source-system connector only after the first connector's
  operational evidence is accepted.
- [ ] Add the next decision domain only after the first domain's policy,
  connector, support, and review controls are stable.
- [ ] Decide whether external workflow dispatch should remain disabled or move
  into a separately approved implementation plan.

## 20. Definition Of Complete

- [ ] The app uses enterprise SSO end to end. There is no product-facing local
  identity picker, password store, or manual token path.
- [ ] The frontend obtains tokens through authorization code plus PKCE or the
  institution's approved portal route.
- [ ] The API validates issuer, audience, expiry, JWKS signature, role, tenant,
  domain, and subject ownership on every protected request.
- [ ] The institution can configure source-system access without writing a
  bespoke CSV export.
- [ ] The first source-system connector is read-only, least-privilege,
  independently approved, monitored, and reversible.
- [ ] Source-to-fact mapping is no-code, immutable after submission, and
  independently reviewed.
- [ ] Connector previews and reconciliation reports avoid broad disclosure of
  subject values.
- [ ] Materialised facts retain source lineage, connector run lineage, mapping
  authority, source version, and source as-of date.
- [ ] Policy release, evidence, fact, connector, identity, review, and support
  workflows have audit events.
- [ ] PostgreSQL RLS is rehearsed with the real serving role.
- [ ] Object storage immutability, backup restoration, key rotation, IdP
  revocation, connector revocation, and incident escalation have been rehearsed.
- [ ] Public and user-facing language presents the product as an enterprise
  implementation in controlled validation, not a demo or mock system.
- [ ] The pilot has named owners, signed acceptance criteria, monitoring,
  support coverage, privacy approval, and a documented human route for affected
  people.
- [ ] CI blocks deployment unless backend tests, mypy, frontend lint, frontend
  build, migration checks, dependency checks, and security gates pass.
- [ ] The institution can run the first bounded decision domain without custom
  CSV scripting, unmanaged identity, or hidden manual decision paths.
