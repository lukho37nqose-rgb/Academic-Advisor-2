# Release Readiness

This document describes the codebase as it is, rather than as an intended
architecture. It is a pre-pilot release gate, not an institutional approval.

## Verified in this repository

- The deterministic evaluator compiles a rule tree, rejects unsupported
  operators, empty or multi-child `NOT` branches, duplicate rule-node IDs, and
  duplicate fact target paths before producing a trace.
- Releases are compiled, signed, integrity-checked before evaluation, and bound
  to an effective period, applicability context, workflow intents, and cited
  policy-source manifest hash.
- Raw evidence is preserved by hash, its bytes are re-verified before use, and
  an extracted or manually proposed fact cannot affect an evaluation until a
  different authorised person accepts it.
- Evaluation is tenant/domain/subject scoped. Idempotency responses are scoped
  to tenant, user, subject, operation, and request content.
- The trace, explanation, citations, decision-review workflow, assisted route,
  institutional timeline, and policy guidance are available through role-gated
  API and frontend surfaces.
- PostgreSQL RLS migrations and append-only audit protections are present. The
  new evidence withdrawal and historical fact-supersession relationships are
  append-only events; neither silently changes an original decision.
- The staging Terraform validates offline. Runtime database credentials are
  injected from Secrets Manager rather than embedded in ECS task-definition
  environment values. State configuration, local variables, and plans are
  ignored by Git.

## Deliberately bounded features

- The no-code intake builds a constrained policy model. Complex calculations,
  nested exceptions, and institution-specific handbook modelling require
  further authoring work and validation against real policy text.
- OCR and external AI are disabled or mock-backed unless explicitly configured.
  Any extracted output remains reviewable candidate material, never decision
  input by itself.
- System-record import is a governed mapping and preview boundary, not a live
  integration with an institutional system of record.
- Workflow selection is implemented and matching rules create held outbox
  records atomically with an evaluation. External delivery remains fail-closed;
  there is no approved dispatcher, destination credential, or reconciliation
  process yet.
- Browser tests use mocked API responses. They demonstrate presentation and
  role boundaries, not a live OIDC-to-FastAPI integration.
- Evidence withdrawal removes operational availability while preserving audit
  material. It is not a legal erasure or a complete retention/deletion service.

## Must be completed with the pilot institution

1. Configure OIDC, claim mappings, provisioning/deprovisioning, tenant roles,
   and an approved frontend hosting or portal-integration route.
2. Provide an institution-owned AWS account, encrypted versioned remote
   Terraform state, DNS, ACM certificate, registry, and secrets-management
   ownership. Run the real Terraform plan in that account.
3. Agree evidence and trace retention, legal hold, object immutability/Object
   Lock, deletion authority, backup retention, restore testing, and key
   lifecycle ownership before real records enter the service.
4. Run Alembic with a migration role, then perform the PostgreSQL RLS rehearsal
   with the production-style application roles. The three skipped local tests
   exist for this environment-dependent check.
5. Define the authoritative source systems, reconciliation rules, staff
   response commitments, review/appeal handoff, notification channel, and
   assisted/offline route.
6. Complete ICT security review: threat-model confirmation, vulnerability and
   penetration testing, monitoring/SIEM integration, incident exercise, backup
   restore exercise, accessibility testing with real users, and privacy/legal
   approval for the pilot's data categories.

## Pilot-safe position

Until those institutional controls are in place, run only synthetic or
approved de-identified shadow cases. The software can demonstrate explanations
and governed reasoning; it must not represent an operative institutional
decision, source-of-record import, or automatic workflow action.
