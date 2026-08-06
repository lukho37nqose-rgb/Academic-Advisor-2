# Institutional Reasoning Engine

The Institutional Reasoning Engine (IRE) is a headless decision runtime for
institutions that need to explain how evidence and policy produced a decision.
It is not a chatbot, student portal, or workflow automation product.

The runtime follows this pipeline:

```text
Preserved evidence -> cited fact proposal -> independent acceptance -> Facts
                   -> RuleGraph evaluation -> ReasoningGraph -> Decision -> Explanation
```

LLMs and OCR may assist staff with source extraction, but their output is never
evaluated directly. An authorised staff member must record a cited candidate
fact and a different authorised person must accept it before it becomes an
evaluation input. Evaluation between those accepted facts and a compiled policy
release is deterministic.

The product principle is **personalise access to institutional reasoning, not
institutional policy**: approved rules remain common, while an authorised person
can see how those rules applied to their own record. See
[Transparency Principles](docs/TRANSPARENCY_PRINCIPLES.md).

## Current State

The current implemented surface includes:

- deterministic evaluation through a domain-neutral engine;
- curriculum and grant domains evaluated without changing the evaluator;
- draft compilation before persistence;
- immutable, signed releases;
- an interpretation register that blocks publication until an authorised policy owner resolves ambiguity with a source citation;
- signed effective periods and applicability selectors, with non-overlap checks, Postgres publication serialisation, replayable policy-selection context, and retained verification bundles for key rotation;
- enforced author/approver separation of duties;
- reasoning traces tied to the rule graph used for evaluation;
- independent fact acceptance, with source quotations, declared-schema checks,
  separation of duties, and source-hash verification immediately before evaluation;
- replay verification that rechecks the source hash, signed release, accepted
  fact lineage, stored trace, and recomputed result;
- Edge-configured Tier 1 metadata edits with tenant/domain RBAC and an audit log;
- no-code institutional policy intake that produces a pending, reviewable draft;
- no-code policy review that renders conditions and citations without exposing JSON;
- public policy guides with citations and a separate human-assistance channel;
- a role-scoped staff inbox with append-only assistance status history, response targets, and retention expiry;
- subject-owned decision-review cases tied to immutable traces, with constrained staff resolution and append-only history;
- subject-to-identity ownership enforcement for evidence, evaluations, and traces;
- handbook PDF source verification with a tenant-scoped durable worker queue,
  resumable page-level checkpoints, bounded retries, and dead-letter retention;
- reviewed OCR proposals that cannot enter a release without a human decision;
- a fixture-backed synthetic pilot rehearsal pack with canonical decision-trace
  digests, including approval, fail-closed, and manual-review paths;
- a one-way, hash-verified system-of-record CSV validation and reconciliation
  boundary that blocks partial or malformed imports;
- governed, immutable system-record mapping configurations with independent
  approval, append-only review history, and forced PostgreSQL tenant RLS;
- fail-closed external workflow handling: signed workflow rules can create held
  outbox records with an evaluation, but nothing is delivered without a durable
  dispatcher;
- production fail-closed configuration checks, non-root container execution,
  separate migration deployment, and health/readiness probes with request IDs;
- a reference React interface for reasoning traces and governance.

It does not yet prove:

- extraction from a real institution's large, messy handbooks;
- production identity-provider integration;
- a complete claims/facts appeals interface;
- integration with a system of record;
- usability by administrators or governed subjects in a live institution.

The next empirical milestone is to model and test one real institution's actual
rules and evidence, including ambiguity, superseded policy, and difficult source
documents.

## Synthetic Pilot Rehearsal

Before any institution authorises source access, the evaluator can be rehearsed
against the fictional fixture pack. It uses the normal release compiler and
decision engine, but never calls an external system or uses personal data.

```powershell
python -m app.sdk.pilot_rehearsal `
  --policy pilot/synthetic/progression_policy.json `
  --suite pilot/synthetic/progression_cases.json `
  --output pilot/synthetic/reports/progression_rehearsal.json
```

The resulting report is deterministic: the policy, each case input, and each
decision-bearing trace have SHA-256 digests. The command exits non-zero when a
golden outcome changes. See [the synthetic rehearsal pack](pilot/synthetic/README.md)
for the boundary between this fixture and a future approved institutional corpus.

## Core And Edge

`app/core` contains domain-neutral evidence, claim, fact, rule, release, and graph
logic. It must not contain concepts such as course, student, grant, faculty, or
credits.

`edge/tenants` contains institution and domain configuration. Tier 1 metadata
targets and allowed fields are declared in each `domain.json`; the shared runtime
does not know what a course or grant programme is.

Tier 1 changes write to `metadata_overrides` and `metadata_quick_edits`. They do
not mutate a compiled `RuleGraph` or an immutable `Release`. Rule-bearing changes
must use the draft, review, approval, and release path.

The frontend is a reference client. External institutional systems consume the
same API and may never expose this interface directly.

## Quickstart

The supported runtime is CPython 3.12. `requirements.in` is the human-reviewed
direct dependency list; `requirements.txt` is the generated, hash-locked
deployment graph. Do not install from `requirements.in` for a normal run.

```powershell
python -m pip install --require-hashes -r requirements.txt
python -m alembic upgrade head
python -m pytest -q
python -m mypy --explicit-package-bases app
python -m uvicorn app.api:app --reload
```

Refresh dependencies only through a reviewed change, then regenerate both
artifacts:

```powershell
python tools/lock_python_dependencies.py
python tools/generate_sbom.py --requirements requirements.txt --output sbom.cdx.json
```

For an older local database created before Alembic was introduced, do not run
`alembic stamp` blindly. Preserve it, inspect its schema and data, then migrate
from a reviewed baseline. The local demo uses a fresh, Alembic-versioned database.

```powershell
cd frontend
npm.cmd ci
npm.cmd run build
npm.cmd run lint
npx.cmd playwright install chromium
npm.cmd run test:e2e
```

`test:e2e` selects a temporary local port and lets Playwright own the Vite
server lifecycle. This avoids a Windows child-process shutdown hang and never
attaches a test run to an already-open development server.

## Configuration

Use `.env.example` as the local configuration inventory. Do not commit secrets.

- `JWT_SECRET_KEY`: local HS256 verification only; production requires OIDC/JWKS.
- `IRE_SUBJECT_ID_CLAIM`: stable institution-owned identifier used to bind a subject to their own record.
- `PUBLIC_RATE_LIMIT_SALT`, `PUBLIC_SUPPORT_RATE_LIMIT_MAX`, `PUBLIC_SUPPORT_RATE_LIMIT_WINDOW_SECONDS`: public assistance abuse controls.
- `SUPPORT_REQUEST_RETENTION_DAYS`: retention period that starts only when a support request is closed.
- `DATABASE_URL`: async SQLAlchemy connection string.
- `IRE_AUTO_CREATE_SCHEMA`: leave `false`; use Alembic for all persistent schemas.
- `REDIS_URL`: production idempotency and request-lock backend.
- `IRE_EDGE_ROOT`: optional path to the Edge tenant/domain registry.
- `REFERENCE_EVIDENCE_MAX_BYTES`: maximum UTF-8 bytes accepted by the small
  reference-text adapter; large documents use governed source intake.
- `REASONING_ENGINE_AI_PROVIDER`: configures an optional proposal-assistance
  boundary; it never supplies facts directly to evaluation.
- `OPENAI_API_KEY`: only for configured extraction/explanation boundaries.
- `GOVERNANCE_PRIVATE_KEY`: release-signing key.
- `S3_BUCKET_NAME`: private object storage for evidence and handbook ingestion; new objects are automatically namespaced under `tenants/{tenant_id}/`.
- `HANDBOOK_UPLOAD_MAX_BYTES`: maximum PDF size accepted by the handbook intake API.

## Production Risks

- New evidence, reasoning traces, claims, and facts are tenant/domain-scoped.
  Pre-migration records are explicitly marked `__legacy_unscoped__` and are not
  available to normal tenants.
- OIDC/JWKS validation and production configuration checks are implemented, but
  deployment still requires the institution's IdP registration, claim mapping,
  key-rotation testing, and access-revocation rehearsal.
- SQLite is for tests; production startup rejects it and requires Postgres,
  Redis, object storage, OIDC, a usable signing key, and reviewed Alembic
  migrations.
- Quick-edit targets are checked against the domain's approved Edge resource
  catalogue before a low-risk metadata overlay is accepted.
- PostgreSQL makes decision-bearing evidence, claims, facts, traces, releases,
  compiled rules, and reviewed fact lifecycles append-only. Some supporting
  audit tables still rely on their specific lifecycle controls and remain
  subject to an institution's independent audit-export requirements.
- Production Postgres serialises governance publication per domain. PostgreSQL
  RLS is enforced with transaction-local tenant context and a non-bypass serving
  role. Institution-managed database roles and independent audit export remain
  live deployment gates for a shared multi-tenant institution.
- Handbook PDFs now retain a hashed source object and page-level worker
  checkpoints. OCR, table reconstruction, and real-institution extraction
  quality are not yet proven and cannot enter a release automatically.
- The reference client supports staff fact entry and independent acceptance, but
  it does not yet provide a complete subject-facing evidence or appeals interface.
- Public assistance controls require a production Redis deployment, an active
  retention scheduler, named response owners, and testing of the assisted or
  offline route before a pilot.

See [PRODUCT_DEFINITION.md](docs/PRODUCT_DEFINITION.md) and
[SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md). The inputs required for a
real institutional pilot are in [PILOT_READINESS.md](docs/PILOT_READINESS.md).
The current documentation map is in [docs/README.md](docs/README.md).
The exact present-tense capability boundary and page visibility by role are in
[CURRENT_CAPABILITIES.md](docs/CURRENT_CAPABILITIES.md). The staged path from
this reference implementation to an institution-controlled environment is in
[DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md).
The control register, adversarial-test evidence, and open pilot gates are in
[the Enterprise Safety Baseline](docs/assurance/README.md).
The access, privacy, and human-review commitments are in
[ACCESS_AND_TRUST.md](docs/ACCESS_AND_TRUST.md). The institutional SSO contract
and rollout checks are in [SSO_ROLLOUT.md](docs/SSO_ROLLOUT.md).
The handbook source and worker boundary are documented in
[HANDBOOK_INGESTION.md](docs/HANDBOOK_INGESTION.md).
The decision-review workflow is documented in
[DECISION_REVIEW.md](docs/DECISION_REVIEW.md).
Policy interpretation, transitional applicability, and effective-period
controls are documented in [POLICY_GOVERNANCE.md](docs/POLICY_GOVERNANCE.md).
The external-AI opt-in and data-minimisation boundary is documented in
[AI_DATA_BOUNDARY.md](docs/AI_DATA_BOUNDARY.md).
The PostgreSQL tenant boundary, public-policy exception, and production role
requirements are documented in [POSTGRES_RLS.md](docs/POSTGRES_RLS.md).
Its executable two-tenant PostgreSQL rehearsal is documented in
[POSTGRES_RLS_REHEARSAL.md](docs/POSTGRES_RLS_REHEARSAL.md).
The UCT case-study boundary and unresolved deployment risks are in
[UCT_PILOT_CHARTER.md](docs/UCT_PILOT_CHARTER.md) and
[UCT_THREAT_MODEL.md](docs/UCT_THREAT_MODEL.md). The deployment sequence is in
[PRODUCTION_DEPLOYMENT.md](docs/PRODUCTION_DEPLOYMENT.md).
The system-of-record import contract and reconciliation boundary are in
[SYSTEM_OF_RECORD_IMPORTS.md](docs/SYSTEM_OF_RECORD_IMPORTS.md).
The external workflow safety boundary is in
[WORKFLOW_DISPATCH.md](docs/WORKFLOW_DISPATCH.md).
The recovery evidence expected before and during a real pilot is in
[RECOVERY_EXERCISES.md](docs/RECOVERY_EXERCISES.md).
