---
name: cacisa-architecture-guardian
description: "Review or guide Cacisa architecture changes so the domain-neutral reasoning core, tenant edge configuration, governance APIs, frontend surfaces, deployment boundaries, and institutional safety invariants remain intact. Use for changes touching app/core, edge/tenants, policy governance, release compilation, ReasoningGraph behavior, external workflows, deployment shape, or architecture docs."
---

# Cacisa Architecture Guardian

## Overview

Use this skill when a task might bend the architecture to fit a feature. The
default posture is to keep institutional specificity at the edge and preserve a
deterministic, replayable core.

## Source Map

Start with:

- `AGENTS.md`
- `docs/CODEX_OPERATING_MODEL.md`
- `docs/SYSTEM_ARCHITECTURE.md`
- `docs/PRODUCT_DEFINITION.md`
- `README.md`

Then load the specific implementation area: `app/core`, `app/services`,
`app/infrastructure`, `edge/tenants`, `frontend/src`, `deploy/terraform`, or
the relevant tests.

## Non-Negotiable Boundaries

- `app/core` remains domain-neutral.
- Tenant/domain policy content belongs under `edge/tenants` or governed source
  records, not hard-coded evaluator branches.
- Rule-bearing changes go through draft, review, approval, signing, release,
  and replayable evaluation.
- Tier 1 metadata edits remain audited overlays and do not mutate RuleGraphs or
  Releases.
- Subject views are projections of common approved policy applied to accepted
  facts. They must not invent subject-specific policy.
- External workflows remain held until an approved dispatcher exists.

## Review Workflow

1. Identify the layer touched by the task.
2. Map the requested change to the architecture invariant it affects.
3. Inspect existing tests for that invariant before editing.
4. Keep new abstractions aligned with existing local patterns.
5. Require explicit tests when changing core evaluation semantics, release
   integrity, tenant boundaries, subject ownership, or deployment gates.
6. Update docs only when behavior or the documented boundary changes.

## Common Failure Modes

- Moving UCT or curriculum assumptions into `app/core`.
- Treating the reference frontend as the product boundary.
- Calling deployment scaffolding "production" without an exercised environment.
- Allowing a convenience API to skip governance separation of duties.
- Turning an explanation or review route into an operative decision path.

## Suggested Checks

For architecture-sensitive changes, run the narrow boundary checks first:

```powershell
python -m pytest -q tests/test_architecture_boundaries.py tests/test_compiler_invariants.py tests/test_decision_safety.py
```

Broaden to the relevant API, assurance, frontend, or migration tests based on
the touched layer.
