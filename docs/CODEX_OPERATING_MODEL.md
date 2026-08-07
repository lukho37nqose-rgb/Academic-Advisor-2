# Cacisa Codex Operating Model

This document gives Codex a persistent engineering operating model for Cacisa.
It is not a complete repository manual. It defines how to separate evidence
from aspiration, architecture from implementation detail, and audits from
changes.

## Operating Thesis

Cacisa builds institutional reasoning infrastructure. The system should make
institutional policy and evidence legible without replacing institutional
judgement or turning probabilistic extraction into an automated decision.

The short rule is:

```text
Evidence -> candidate fact proposal -> independent acceptance or rejection
         -> accepted facts -> signed release -> deterministic evaluation
         -> ReasoningGraph -> decision and explanation
```

## Truth Hierarchy

Use this order when sources disagree:

1. Executed source code and test results from this checkout.
2. Application source, migrations, fixtures, and configuration.
3. Current documentation in `README.md` and `docs/`.
4. Prior task summaries, chat references, plans, and intentions.

Documentation can describe intended architecture. It does not prove operational
status. A prior assistant claim is never evidence by itself.

## Evidence Labels

Use these labels in audits, readiness reviews, and implementation summaries:

| Label | Meaning |
| --- | --- |
| Exercised end-to-end | A representative user or system flow ran through the real stack claimed. |
| API-tested | HTTP/API behavior is covered, but not necessarily through the full UI or deployed stack. |
| Unit-tested | Local units or services are covered without proving integration. |
| Implemented but unexecuted | Code exists, but no matching test or run evidence was found. |
| Configuration-dependent | The behavior depends on environment, secrets, external services, or deployment settings not proven locally. |
| Mock-backed | Tests use fakes or fixtures and do not prove the real provider/system. |
| PostgreSQL-only, unverified | Code or docs depend on PostgreSQL behavior that was not exercised against PostgreSQL. |
| Missing | The behavior, route, migration, UI, or control was not found. |

Do not use "done", "deployed", "production-ready", or "verified" without
matching evidence.

## Architectural Invariants

- Keep `app/core` domain-neutral. Institution, tenant, curriculum, grant,
  faculty, UCT, demo, and pilot vocabulary belongs in `edge/`, `pilot/`, docs,
  adapters, services, or frontend copy.
- Preserve Evidence, Claim, Fact, Release, RuleGraph, ReasoningGraph, and
  explanation as distinct concepts.
- Treat AI, OCR, and parsing as proposal assistance unless a cited human review
  path accepts the result.
- Keep decision-time evaluation deterministic. A model may not decide whether a
  subject satisfies policy.
- Preserve historical explainability. Replays must bind to the evidence hashes,
  accepted facts, release, source manifest, and policy-selection context used at
  the time.
- Keep external workflow dispatch fail-closed. A signed workflow rule may create
  a held outbox record, but external writes require a separate approved
  dispatcher.
- Treat Terraform, Docker, and environment examples as deployment intent until
  a real deployment or rehearsal proves them.
- Treat SQLite test success as local confidence only. PostgreSQL-specific
  controls, RLS, locking, and immutability require PostgreSQL evidence.

## Skill Routing

Use the repository-local skills in `.codex/skills/`:

| Skill | Use it for |
| --- | --- |
| `cacisa-verification-auditor` | Read-only capability, readiness, evidence, deployment, and audit claims. |
| `cacisa-architecture-guardian` | Core/edge boundaries, domain neutrality, frontend/API/deployment shape, and invariant review. |
| `cacisa-reasoning-integrity` | Evidence, claims, facts, OCR, AI assistance, replay, explanations, and subject-position semantics. |
| `cacisa-migration-guardian` | Alembic, persistent data, PostgreSQL RLS, deployment migrations, schema safety, and rollback risk. |

Use more than one skill when the work crosses boundaries. For example, a new
fact-ingestion migration should use both reasoning integrity and migration
guardian.

## Audit Boundary

When the user asks to audit, inspect, verify, review status, assess readiness,
or classify evidence:

- Do not patch code, docs, fixtures, migrations, or tests unless the user
  explicitly asks for fixes.
- Do not silently repair broken evidence while auditing it.
- Do not convert an intended architecture into a claim about implemented
  behavior.
- Do not run destructive commands or reset git state.
- Report what is proven, what is merely present, and what remains unknown.

If an audit reveals a fix, present it as a proposed change with the files and
tests needed to prove it.

## Implementation Boundary

When the user asks to implement:

- Inspect the existing design and tests first.
- Keep changes scoped to the relevant layer.
- Add or update tests when behavior, architecture, security, migration, or user
  workflow semantics change.
- Keep docs in sync with actual behavior, especially present-tense capability
  claims.
- Report any verification that could not be run and why.

## Current Invariant Tests

`tests/test_architecture_boundaries.py` checks that the repository-level Codex
operating model exists and that `app/core` does not acquire obvious
institution-specific policy vocabulary.

## Useful Next Invariant Tests

These are good candidates when their surrounding code changes:

- Assert Alembic has a single expected head and migrations do not bypass
  reviewed release, fact, evidence, and trace immutability.
- Assert frontend role visibility remains a projection of
  `/api/v1/session/capabilities`, not hard-coded permission truth.
- Assert any PostgreSQL RLS claim points to an executed disposable PostgreSQL
  rehearsal, not only SQLite tests.
- Assert external workflow rules can only create held outbox records unless an
  approved dispatcher path and tests exist.
