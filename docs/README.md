# Documentation Index

This directory describes the current Institutional Reasoning Engine and its
deployment boundaries. It is not an archive of earlier product thinking. When a
document no longer represents the implemented system, update it or remove it.

## Start Here

| Document | Purpose |
| --- | --- |
| [PRODUCT_DEFINITION.md](PRODUCT_DEFINITION.md) | Product identity, reasoning thesis, proven boundaries, and open validation gates. |
| [CURRENT_CAPABILITIES.md](CURRENT_CAPABILITIES.md) | Plain-language account of what the application does today and what it does not do yet. |
| [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) | Core evidence, fact, policy, release, and graph architecture. |
| [CODEX_OPERATING_MODEL.md](CODEX_OPERATING_MODEL.md) | Persistent Codex truth model, skill routing, audit boundary, and invariant-test guidance. |
| [TRANSPARENCY_PRINCIPLES.md](TRANSPARENCY_PRINCIPLES.md) | Subject-facing explanation principles and safety constraints. |
| [assurance/README.md](assurance/README.md) | Enterprise safety baseline and control evidence index. |

## Implementation Areas

| Document | Purpose |
| --- | --- |
| [POLICY_GOVERNANCE.md](POLICY_GOVERNANCE.md) | Draft, ambiguity, approval, release, and applicability controls. |
| [HANDBOOK_INGESTION.md](HANDBOOK_INGESTION.md) | Handbook source upload, hashing, page extraction, and review boundary. |
| [OCR_REVIEW.md](OCR_REVIEW.md) and [OCR_ASSURANCE.md](OCR_ASSURANCE.md) | OCR as untrusted proposal assistance, not automatic rule creation. |
| [SYSTEM_OF_RECORD_IMPORTS.md](SYSTEM_OF_RECORD_IMPORTS.md) | Approved source-record mappings, CSV fallback, and enterprise connector boundary. |
| [INSTITUTIONAL_TIMELINE.md](INSTITUTIONAL_TIMELINE.md) | Certified institutional context as explanatory history. |
| [DECISION_REVIEW.md](DECISION_REVIEW.md) | Subject-owned review cases tied to immutable decision traces. |
| [WORKFLOW_DISPATCH.md](WORKFLOW_DISPATCH.md) | Signed workflow rules and held outbox records; no external delivery yet. |
| [DURABLE_BACKGROUND_WORKER.md](DURABLE_BACKGROUND_WORKER.md) | PostgreSQL-backed work ledger and optional SQS wakeup signal. |

## Deployment And Operations

| Document | Purpose |
| --- | --- |
| [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md) | Production configuration and release gates. |
| [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | Institution-controlled deployment sequence. |
| [DEPLOYMENT_SURFACES.md](DEPLOYMENT_SURFACES.md) | Public, reference, staging, tenant, and provider surfaces. |
| [AWS_PLATFORM_ARCHITECTURE.md](AWS_PLATFORM_ARCHITECTURE.md) | Recommended AWS account and service architecture. |
| [ENTERPRISE_IMPLEMENTATION_TODO.md](ENTERPRISE_IMPLEMENTATION_TODO.md) | Step-by-step TODO for enterprise SSO, read-only source-system connectors, and pilot launch hardening. |
| [POSTGRES_RLS.md](POSTGRES_RLS.md) and [POSTGRES_RLS_REHEARSAL.md](POSTGRES_RLS_REHEARSAL.md) | PostgreSQL tenant isolation and executable rehearsal. |
| [SSO_ROLLOUT.md](SSO_ROLLOUT.md) | Institution-owned identity integration checks. |
| [ACCESS_AND_TRUST.md](ACCESS_AND_TRUST.md) | Public access, assisted routes, retention, and review commitments. |

## Pilot-Specific Material

| Document | Purpose |
| --- | --- |
| [PILOT_READINESS.md](PILOT_READINESS.md) | Inputs needed before any controlled institutional pilot. |
| [PILOT_DEPLOYMENT_RUNBOOK.md](PILOT_DEPLOYMENT_RUNBOOK.md) | Technical rehearsal sequence for a limited pilot. |
| [UCT_PILOT_CHARTER.md](UCT_PILOT_CHARTER.md) and [UCT_THREAT_MODEL.md](UCT_THREAT_MODEL.md) | UCT case-study boundaries. They do not claim UCT approval. |
| [UCT_ICTS_DISCOVERY_REQUEST.md](UCT_ICTS_DISCOVERY_REQUEST.md) | Plain-language ICTS request fields for possible UCT controlled pre-production validation. |
| [HUMANITIES_LOCAL_REHEARSAL.md](HUMANITIES_LOCAL_REHEARSAL.md) | Developer-only rehearsal procedure for local Humanities material. |

## Company And Public Presence

| Document | Purpose |
| --- | --- |
| [CACISA_BRAND_SYSTEM.md](CACISA_BRAND_SYSTEM.md) | Brand identity rules for Cacisa Systems. |
| [CACISA_ONLINE_PRESENCE.md](CACISA_ONLINE_PRESENCE.md) | Company, demo, tenant, provider, and status surface model. |
