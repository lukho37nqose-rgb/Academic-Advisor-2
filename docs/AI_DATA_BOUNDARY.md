# AI Data Boundary

The deterministic evaluator does not require an external AI provider. The
default provider is `mock`, and merely setting an API key does not enable data
transfer. AI may assist only with extraction proposals or an explanation after
the decision logic has completed; it never selects a rule, resolves an
ambiguity, creates an accepted fact, or changes an outcome.

## Production gate

External AI processing is disabled unless all of the following are present:

- `REASONING_ENGINE_AI_PROVIDER=openai`;
- `OPENAI_API_KEY` supplied at runtime from the institution's secret manager;
- `IRE_ALLOW_EXTERNAL_AI_PROCESSING=true`; and
- `IRE_EXTERNAL_AI_APPROVAL_REFERENCE`, identifying the institution's approved
  privacy, procurement, and data-processing decision.

Production startup fails if any of these requirements are absent. This is a
configuration guard, not proof that an institution has completed its legal or
ethical review; the approval reference must be reviewable in the institution's
own records.

## Data minimisation

Only the content necessary for the requested extraction proposal or trace
explanation may cross the approved provider boundary. Extraction refuses to
send evidence above `EXTERNAL_AI_MAX_INPUT_BYTES` (200,000 bytes by default)
and returns no decision input. It does not truncate and continue, because
partial evidence can produce a misleading proposal.

Before enabling an external provider, the institution must approve the data
categories, provider region, retention and training terms, sub-processors,
incident reporting, deletion route, and an equivalent human route for people
whose information must not use that provider. A provider approval never changes
the access controls, retention limits, source-review, or decision-review duties
elsewhere in the system.
