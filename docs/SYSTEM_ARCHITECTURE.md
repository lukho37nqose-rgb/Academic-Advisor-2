# Institutional Reasoning Protocol
**Specification Version:** 1.0.0  
**Status:** Current implementation specification with controlled-pilot gates

## 1. Abstract
The Institutional Reasoning Protocol (IRP) defines a standardized, language-agnostic architecture for evaluating individuals or entities against complex, evolving institutional policies. It explicitly separates the epistemological resolution of facts from the deterministic execution of rules.

Its primary goal is to make institutional decisions **deterministic,
cryptographically tamper-evident, and reproducibly auditable** within the
limits of the evidence, policy model, and operational controls supplied.

---

## 2. The Epistemological Pipeline (Data Ingestion)
To preserve the integrity of appeals and audits, the protocol strictly models the progression from raw data to accepted truth.

### 2.1 Evidence
* **Definition:** A preserved data object provided to the system. It may be an
  uploaded PDF, a JSON payload from an ERP system (e.g., PeopleSoft), or a user
  form submission.
* **Constraint:** Evidence is SHA-256 hashed at ingestion and re-verified before
  evaluation and replay. The serving database treats its evidence record as
  append-only; deployment also requires object-store retention/versioning.

### 2.2 Claim
* **Definition:** A candidate assertion about a piece of evidence. It may be
  recorded by an authorised staff member or proposed by a deterministic parser
  or probabilistic LLM for staff review.
* **Structure:** A Claim asserts that a specific `target_path` (e.g., `academic.gpa`) holds a specific `asserted_value` (e.g., `3.8`).
* **Constraint:** An automated claim is proposal assistance only. It cannot
  become a decision input until it is recorded against source provenance,
  constrained to an approved schema field, and independently accepted.

### 2.3 Fact
* **Definition:** A canonical decision input established by independent human
  acceptance of a cited candidate fact.
* **Mechanism:** One accepted proposal per evidence and target path is materialised
  as a fact for evaluation. It cannot be overwritten. Corrections use a governed
  successor-fact relationship that preserves the earlier fact and creates a new
  evaluation path.
* **Constraint:** Facts retain their supporting claim, evidence hash, tenant,
  domain, and reasoning trace lineage. They are append-only in PostgreSQL.

---

## 3. The Execution Protocol (The Three Graphs)
The protocol abandons linear evaluation in favor of explicit graph generation.

### 3.1 RuleGraph (Static Policy)
* **Definition:** The static, compiled bytecode representing an institution's policy for a given domain and version.
* **Mechanism:** Policies are authored in human-readable SDKs or visual builders, but compile down into a rigorous `ExpressionNode` AST (Abstract Syntax Tree) supporting logical grouping (`AND`, `OR`, `NOT`).
* **Constraint:** A RuleGraph is tied to an immutable `Release`. The Release MUST be cryptographically signed to prove governance approval (Author vs. Approver separation of duties), and the signed payload binds policy metadata, rule logic, workflow intents, and a canonical cited-source manifest hash.

### 3.2 ReasoningGraph (Dynamic Trace)
* **Definition:** The canonical artifact generated when a Subject is evaluated. 
* **Mechanism:** The Reasoning Engine takes the `RuleGraph` and the accepted `Facts`, and executes the logic. It generates a graph containing:
  *   **Nodes:** `fact`, `rule_evaluation`, `conclusion`.
  *   **Edges:** `evaluates_to`, `depends_on`.
* **Constraint:** The ReasoningGraph IS the evaluation. The final true/false decision is merely a flattened projection of the `conclusion` node. The graph MUST capture the exact context (Tenant, Subject, Release, Timestamp) under which it was generated.

* **Subject-view constraint:** A personal position view is a read-only
projection of this trace. It may make the application of the shared release
legible to the affected subject, but it MUST NOT create a subject-specific
policy, alter the release, or represent a human-review trigger as a final
institutional decision.

### 3.3 External Workflow Boundary (Post-Evaluation)
* **Definition:** A reserved integration boundary for any future action triggered
  after a reasoning graph.
* **Current constraint:** Workflow rules are reviewed release content. When a
  signed workflow rule matches an evaluation, the runtime creates a tenant-
  scoped `HELD` outbox record in the same transaction as the reasoning trace.
  No external delivery is performed. A separate, approved dispatcher is required
  before any institutional write is enabled.

---

## 4. Operational Boundaries

### 4.1 Headless APIs & Adapters
The Engine is infrastructure. It does not own the frontend or the database of record. External systems use an **Adapter Pattern** to ingest their specific formats into the `Evidence` interface.

### 4.2 LLM Quarantine
Probabilistic Large Language Models MUST be strictly quarantined to the system's boundaries:
1.  **Extractor Boundary:** Translating unstructured Evidence into structured Claims.
2.  **Explainer Boundary:** Translating the deterministic ReasoningGraph trace into natural language prose for human consumption.
The core Reasoning Engine MUST remain 100% deterministic and mathematically pure.

### 4.3 Independent Queryability
To support institutional appeals processes, the system MUST expose independent access endpoints for all epistemological stages:
*   `GET /claims/{id}`
*   `GET /facts/{id}`
*   `GET /reasoning/{id}`

### 4.4 Core and Edge Boundary

Core contains only the domain-neutral decision runtime. Institution-specific
terminology, schemas, metadata policy, extraction configuration, and authored
rules belong under Edge configuration. Adding a curriculum, grant, procurement,
or admissions domain must not require changes to the evaluator.

Tier 1 metadata edits are also Edge-defined. They operate as audited presentation
overlays and cannot mutate a RuleGraph or Release.

### 4.5 Large Document Boundary

Large policy PDFs are immutable evidence objects, not synchronous API payloads.
A production ingestion path stores the original object, hashes it, queues
page-range extraction, checkpoints progress, preserves page-level provenance,
and requires human validation before extracted policy can become a draft.
Uploading or parsing a multi-hundred-page handbook inside a request handler is
outside the supported architecture.

### 4.6 Identity Boundary

Production authentication uses issuer, audience, expiry, and JWKS validation.
The identity provider must issue tenant, role, and assigned-domain claims; these
claims are enforced at domain access boundaries. The local HS256 path exists only
for development and refuses to run when `IRE_ENV` is not a development environment.
