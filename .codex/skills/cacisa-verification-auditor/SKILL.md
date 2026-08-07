---
name: cacisa-verification-auditor
description: "Audit Cacisa implementation, readiness, deployment, safety, and capability claims against source code and executed evidence. Use when asked to verify, audit, inspect, assess current status, review TODO/progress/readiness, or classify whether behavior is exercised end-to-end, API-tested, unit-tested, implemented but unexecuted, configuration-dependent, mock-backed, PostgreSQL-only unverified, or missing. Preserve read-only audit boundaries and do not patch code or docs unless the user explicitly asks for fixes."
---

# Cacisa Verification Auditor

## Overview

Use this skill to prevent status inflation. Verify what the repository actually
proves, then label each claim with the strongest support found.

## Source Map

Load only the files needed for the claim under review:

- `AGENTS.md`
- `docs/CODEX_OPERATING_MODEL.md`
- `README.md`
- `docs/CURRENT_CAPABILITIES.md`
- `docs/PRODUCT_DEFINITION.md`
- `docs/assurance/README.md`
- Relevant source files, tests, migrations, frontend tests, or deployment docs.

## Audit Workflow

1. Restate the claim being verified.
2. Preserve the read-only boundary. Do not patch or clean files during an audit.
3. Inspect source code and tests before relying on docs.
4. Run focused non-destructive checks when practical.
5. Classify each claim using the evidence labels in
   `docs/CODEX_OPERATING_MODEL.md`.
6. Distinguish "implemented", "tested", "exercised", "deployed", and
   "production-ready".
7. Report gaps as proposed next evidence, not as hidden repairs.

## Red Lines

- Do not call Terraform, Docker, or environment files deployed evidence.
- Do not call PostgreSQL controls verified when only SQLite tests ran.
- Do not treat mock-backed tests as proof of external integrations.
- Do not infer operational identity-provider, object-storage, Redis, OCR, or
  notification readiness without executed evidence.
- Do not convert README or prior-chat claims into verified facts.

## Report Shape

Prefer a compact table:

| Claim | Status label | Evidence | Gap or next proof |
| --- | --- | --- | --- |

End with the checks that were run and checks that were not run.
