---
name: cacisa-migration-guardian
description: "Guard Cacisa schema, Alembic, PostgreSQL RLS, persistence, and deployment migration safety. Use when adding or reviewing migrations, persistent tables, immutable records, tenant scoping, deployment infrastructure, startup gates, rollback plans, data backfills, or claims that database/deployment controls are verified."
---

# Cacisa Migration Guardian

## Overview

Use this skill for persistent-state and deployment safety. A migration is not
only a schema diff; it is a historical decision about how existing evidence,
facts, releases, traces, and tenant records remain explainable.

## Source Map

Start with:

- `AGENTS.md`
- `docs/CODEX_OPERATING_MODEL.md`
- `README.md`
- `docs/PRODUCTION_DEPLOYMENT.md`
- `docs/DEPLOYMENT_GUIDE.md`
- `docs/POSTGRES_RLS.md`
- `docs/POSTGRES_RLS_REHEARSAL.md`
- `docs/RELEASE_READINESS.md`
- `alembic/versions/`
- `app/infrastructure/database.py`
- Relevant persistence and assurance tests.

## Migration Rules

- Do not run `alembic stamp` blindly on an existing database.
- Do not reset, drop, or rewrite user data without explicit instruction and a
  reviewed migration plan.
- Keep decision-bearing evidence, claims, facts, releases, compiled rules,
  traces, and reviewed fact lifecycles append-only.
- Preserve tenant and domain scope on new persistent records.
- Treat SQLite as a local compatibility check only. RLS, JSONB, locking,
  transaction-local tenant context, and serving-role behavior require
  PostgreSQL evidence.
- Keep migrations separate from app startup in production.
- Treat Terraform and Docker as infrastructure definition until an executed
  deployment or rehearsal proves the environment.

## Review Workflow

1. Inspect current git state and existing untracked or rejected files without
   cleaning them.
2. Inspect the current Alembic revision chain before adding or reviewing a
   migration.
3. Identify affected tables, historical records, tenant scope, indexes,
   constraints, and rollback risk.
4. For implementation tasks, add a new migration rather than editing old applied
   migration intent unless the repository clearly treats it as unreleased.
5. Add focused tests for new persistent behavior. Use PostgreSQL rehearsal tests
   before claiming PostgreSQL-specific controls are verified.
6. Update docs only when deployment or operational truth changes.

## Evidence Labels

Use the labels from `docs/CODEX_OPERATING_MODEL.md`. In particular:

- Terraform present: implemented infrastructure definition, not deployed.
- Alembic file present: implemented migration, not applied.
- SQLite migration test: local migration confidence, not PostgreSQL control
  verification.
- Disposable PostgreSQL rehearsal: PostgreSQL-exercised for the covered path.

## Suggested Checks

Choose the relevant subset:

```powershell
python -m alembic upgrade head
python -m pytest -q tests/test_production_readiness.py tests/integration/test_postgres_rls.py
```

Only run destructive PostgreSQL rehearsals against an explicitly disposable
database.
