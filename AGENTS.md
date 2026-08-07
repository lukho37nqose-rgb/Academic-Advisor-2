# Cacisa Engineering Constitution

This repository is the Institutional Reasoning Engine for Cacisa. Treat
`AGENTS.md` as the compact constitution for how to work here, not as the full
source of project truth. Load deeper context from `docs/` and the relevant
skill before making claims or changes.

## Product Thesis

Cacisa makes institutional rules legible, deterministic, explainable, and
auditable to the people governed by them.

The core intervention is institutional legibility.

## Architecture Boundary

The reasoning core is domain-neutral. Tenant-specific policy, institutional
language, documents, UI copy, and configuration belong at the edge.

Do not encode UCT-specific, curriculum-specific, grant-specific, or tenant-
specific rules into `app/core`.

## Epistemic Model

Preserved evidence -> cited candidate fact proposal -> independent acceptance
or rejection -> decision-bound facts -> deterministic RuleGraph evaluation ->
ReasoningGraph -> decision and explanation.

Do not collapse Evidence, Claims, Facts, policy Releases, and ReasoningGraphs
into one concept.

## Decision Integrity

AI may assist extraction, triage, and explanation at governed boundaries. AI
must not determine the final policy decision. Decision-time evaluation must
remain deterministic and replayable from accepted facts and a signed release.

Historical decisions must remain explainable from the exact governed inputs and
policy artefacts used at the time. Never silently replace historical inputs
with current facts, current policy, or repaired evidence.

## Verification Doctrine

Source code and executable tests outrank documentation. Presence of code does
not imply operational status.

Use these evidence labels:

- Exercised end-to-end
- API-tested
- Unit-tested
- Implemented but unexecuted
- Configuration-dependent
- Mock-backed
- PostgreSQL-only, unverified
- Missing

Never call infrastructure deployed merely because Terraform exists. Never call
PostgreSQL controls verified when tests ran only against SQLite.

## Change Discipline

When instructed to audit, inspect, document, or verify, do not alter
application code, migrations, fixtures, or docs unless the user explicitly asks
for implementation. Report findings and proposed fixes separately.

Avoid destructive git operations. Do not reset, checkout, clean, or remove
unrelated files without explicit user instruction.

## Where Truth Lives

- `README.md`: current project overview and run commands.
- `docs/CODEX_OPERATING_MODEL.md`: Codex truth model, status labels, and skill
  routing.
- `docs/PRODUCT_DEFINITION.md`: product identity and proven/not-proven boundary.
- `docs/CURRENT_CAPABILITIES.md`: present-tense capability boundary.
- `docs/SYSTEM_ARCHITECTURE.md`: reasoning protocol and core/edge architecture.
- `docs/assurance/README.md`: enterprise safety baseline and evidence index.
- `.codex/skills/`: repository-specific Codex workflows.

## Expected Checks

For backend or architecture changes, prefer focused tests first:

```powershell
python -m pytest -q tests/test_architecture_boundaries.py tests/test_compiler_invariants.py tests/test_decision_safety.py
```

For broader backend changes, run:

```powershell
python -m pytest -q
python -m mypy --explicit-package-bases app
```

For frontend changes, run from `frontend/`:

```powershell
npm.cmd run build
npm.cmd run lint
npm.cmd run test:e2e
```
