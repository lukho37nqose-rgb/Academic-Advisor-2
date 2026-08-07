---
name: cacisa-reasoning-integrity
description: "Protect Cacisa's epistemic and decision-integrity model. Use when working on evidence, claims, facts, fact acceptance, OCR or LLM proposals, handbook ingestion, source hashes, replay verification, explanations, subject position views, human review, or any change that might collapse evidence, proposals, facts, deterministic decisions, and historical traces."
---

# Cacisa Reasoning Integrity

## Overview

Use this skill when work touches what the system knows, proposes, accepts,
decides, replays, or explains.

## Source Map

Load the relevant subset:

- `AGENTS.md`
- `docs/CODEX_OPERATING_MODEL.md`
- `docs/SYSTEM_ARCHITECTURE.md`
- `docs/AI_DATA_BOUNDARY.md`
- `docs/HANDBOOK_INGESTION.md`
- `docs/OCR_REVIEW.md`
- `docs/SYSTEM_OF_RECORD_IMPORTS.md`
- `docs/DECISION_REVIEW.md`
- `app/core/models.py`
- `app/core/engine.py`
- `app/core/replay.py`
- Relevant `app/services/*` and tests.

## Epistemic Distinctions

- Evidence is preserved source material with a hash and provenance.
- A Claim or proposal is not a decision input.
- A Fact is an accepted, governed decision input with lineage.
- A Release is signed policy content, not mutable runtime preference.
- A ReasoningGraph is the decision trace, not explanatory decoration.
- An explanation is generated after the trace and may not affect evaluation.

## Review Workflow

1. Identify which epistemic object the change touches.
2. Check that the change does not skip independent acceptance, source citation,
   source hashing, or separation of duties.
3. Ensure missing or uncertain facts route to human review rather than silent
   failure or invented certainty.
4. Preserve append-only history. Corrections should use successor relationships
   or explicit review events, not mutation of historical inputs.
5. Keep AI and OCR outputs quarantined as proposals until a human route accepts
   or rejects them.
6. Ensure replay remains bound to the original evidence hash, accepted facts,
   release, policy-selection context, and trace.

## Good Test Targets

Use the narrowest relevant tests first:

```powershell
python -m pytest -q tests/test_engine.py tests/test_replay_verifier.py tests/test_evidence_disposition.py tests/test_decision_safety.py
```

For AI, OCR, handbook, or system-record changes, add the relevant API and
assurance tests before claiming the boundary is verified.

## Red Lines

- Do not let LLM output become a Fact directly.
- Do not let an explanation alter the decision.
- Do not overwrite accepted evidence or facts to make a replay pass.
- Do not present a human-review trigger as a final institutional decision.
- Do not let current policy or current source records silently replace a
  historical decision's inputs.
