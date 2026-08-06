# UCT Shadow-Pilot Briefing Pack

## 1. The Problem & The Pilot Question
University policy and curriculum rules are complex, frequently amended, and distributed across multiple handbooks. This creates risk around consistent, transparent, and equitable decision-making for students.

**The Pilot Question:**
Can one bounded UCT decision be faithfully represented from authoritative, versioned institutional material and explained back to the affected person with the exact release and source citations that drove the result?

## 2. The Shadow-Only Boundary
This pilot is strictly a **shadow evaluation**.
- **No Live Impact:** It will not create, alter, recommend as final, or automatically communicate any outcome that affects a student, staff member, or applicant.
- **No Write-Back:** There is no write-back to PeopleSoft or any other UCT system of record.
- **No Real Student Data (Initially):** We will begin with synthetic cases. Only after privacy approval will we use approved de-identified or consented material.
- **Human Authority:** A human institutional process remains the sole source of an operative decision.

## 3. Architecture & Data Flow
The Curriculum Reasoning Engine (IRE) is a containerized Python API (FastAPI) and React frontend, backed by PostgreSQL and Redis.

**Data Flow:**
1. **Policy Ingestion:** Authoritative PDFs are ingested, hash-verified, and reviewed by a human. Object Lock is a deployment prerequisite before treating source storage as write-once.
2. **Governance:** A Policy Owner drafts rules based on the source. An Independent Approver signs the release.
3. **Evaluation:** The deterministic engine evaluates facts against the signed release. AI is *never* used to make a decision.
4. **Explanation:** The engine produces a trace linking the outcome to the exact policy citations.

## 4. Role Matrix & Separation of Duties
The system enforces strict separation of duties. UCT must name individuals for these roles:

| Role | Responsibility |
| :--- | :--- |
| **Policy Owner** | Confirms meaning, authoritative version, and effective dates of rules. |
| **Independent Approver** | Approves/rejects a compiled policy release (cannot be the author). |
| **System Owner** | Owns system-of-record integration and operational change window. |
| **Identity Owner** | Approves OIDC claims, access revocation, and staff role assignment. |
| **Privacy/Security Lead** | Approves data categories, retention, hosting, and incident path. |
| **Student-Support Lead** | Approves the public explanation and assisted/offline route. |
| **Appeals Owner** | Defines how a person challenges missing evidence or source errors. |

## 5. Current Controls & Explicit Gaps
**What we have built:**
- Deterministic evaluation engine (no AI decisions).
- Cryptographically signed policy releases.
- PostgreSQL Row-Level Security (RLS) for tenant isolation.
- Idempotency and replay verification.
- Current automated backend tests pass; browser authentication tests require the institution's configured OIDC test flow.

**What we need ICTS to provide (The Gaps):**
- Approved hosting route for a Python container API and React frontend.
- Non-production PostgreSQL, Redis, and private object storage.
- OIDC owner and process for issuing test tokens.
- Group-to-role mapping for the seven test roles.
- Separate database identities (migration, application, break-glass).
- Security review, vulnerability-testing, and change-control process.
- DNS/HTTPS staging route after security approval.
- Answers for the institutional shadow preflight manifest:
  identity claims, environment ownership, operational controls, source-system
  export shape, and named support/review owners.

## 6. The Ask
We are requesting a **technical discovery session** and a **non-production, UCT-controlled shadow-pilot environment**. 

We are *not* requesting live PeopleSoft access, student bulk data, write-back permissions, or external AI approval at this stage. We want to prove the concept in a safe, isolated environment.
