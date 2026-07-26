# Institutional Reasoning Protocol
**Specification Version:** 1.0.0  
**Status:** VALIDATED PROTOTYPE

## 1. Abstract
The Institutional Reasoning Protocol (IRP) defines a standardized, language-agnostic architecture for evaluating individuals or entities against complex, evolving institutional policies. It explicitly separates the epistemological resolution of facts from the deterministic execution of rules.

Its primary goal is to make institutional decisions **deterministic,
cryptographically tamper-evident, and reproducibly auditable** within the
limits of the evidence, policy model, and operational controls supplied.

---

## 2. The Epistemological Pipeline (Data Ingestion)
To preserve the integrity of appeals and audits, the protocol strictly models the progression from raw data to accepted truth.

### 2.1 Evidence
* **Definition:** An immutable blob of data provided to the system. It may be an uploaded PDF, a JSON payload from an ERP system (e.g., PeopleSoft), or a user form submission.
* **Constraint:** Evidence MUST be cryptographically hashed (SHA-256) at the exact moment of ingestion. It is never modified.

### 2.2 Claim
* **Definition:** An assertion derived from a piece of Evidence by an Extractor (which may be a deterministic parser or a probabilistic LLM). 
* **Structure:** A Claim asserts that a specific `target_path` (e.g., `academic.gpa`) holds a specific `asserted_value` (e.g., `3.8`).
* **Constraint:** Every Claim MUST carry an `extraction_confidence` score [0.0 - 1.0] and a `source_trust_level` score representing the inherent reliability of the Evidence type.

### 2.3 Fact
* **Definition:** A canonical truth established by the system.
* **Mechanism:** The Conflict Engine evaluates all competing Claims for a given `target_path`. It weights them using weighted-confidence model based on confidence and trust levels to select a `resolved_value`.
* **Constraint:** A Fact MUST maintain strict referential integrity, recording exactly which `supporting_claim_ids` it accepted and which `rejected_claim_ids` it discarded. Both claims and facts are retained against the tenant-scoped ReasoningGraph that used them.

---

## 3. The Execution Protocol (The Three Graphs)
The protocol abandons linear evaluation in favor of explicit graph generation.

### 3.1 RuleGraph (Static Policy)
* **Definition:** The static, compiled bytecode representing an institution's policy for a given domain and version.
* **Mechanism:** Policies are authored in human-readable SDKs or visual builders, but compile down into a rigorous `ExpressionNode` AST (Abstract Syntax Tree) supporting logical grouping (`AND`, `OR`, `NOT`).
* **Constraint:** A RuleGraph is tied to an immutable `Release`. The Release MUST be cryptographically signed to prove governance approval (Author vs. Approver separation of duties).

### 3.2 ReasoningGraph (Dynamic Trace)
* **Definition:** The canonical artifact generated when a Subject is evaluated. 
* **Mechanism:** The Reasoning Engine takes the `RuleGraph` and the accepted `Facts`, and executes the logic. It generates a graph containing:
  *   **Nodes:** `fact`, `rule_evaluation`, `conclusion`.
  *   **Edges:** `evaluates_to`, `depends_on`.
* **Constraint:** The ReasoningGraph IS the evaluation. The final true/false decision is merely a flattened projection of the `conclusion` node. The graph MUST capture the exact context (Tenant, Subject, Release, Timestamp) under which it was generated.

### 3.3 WorkflowGraph (Post-Evaluation)
* **Definition:** The event-driven actions triggered by the result of a ReasoningGraph.
* **Mechanism:** If the `conclusion` node passes, specific actions (e.g., "Generate Letter", "Notify SIS") are placed into a job queue for asynchronous execution.

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
