# Institutional Reasoning Engine: Product Definition

## Identity

The IRE is decision infrastructure for institutions that cannot adequately
explain their own decisions to the people governed by them.

It takes institutionally governed policy and subject evidence, then produces a
decision that is:

- deterministic for the same accepted facts and release;
- governed by institutional staff rather than code changes by the platform team;
- reproducible against the exact policy release used;
- auditable through evidence, claims, facts, rules, and graph dependencies;
- explainable in plain language with citations to the rules that drove it.

The frontend is not the product. The runtime sits above systems of record and can
be consumed by their existing interfaces.

## Transparency Principle

**The IRE personalises access to institutional reasoning, not institutional
policy.** An approved policy release remains common to everyone it governs.
The system combines that common release with a person's authorised record to
produce a traceable personal view of how the policy applied in their case. It
does not create a private rule, replace institutional judgement, or conceal a
human-review requirement as an automated outcome.

See [TRANSPARENCY_PRINCIPLES.md](TRANSPARENCY_PRINCIPLES.md) for the subject
experience and safety boundaries that follow from this principle.

## Architectural Thesis

Opacity is the mechanism; legibility is the intervention.

```text
Current decision path:

Evidence + signed policy release
  -> extraction
  -> claims
  -> conflict resolution
  -> accepted facts
  -> deterministic RuleGraph evaluation
  -> ReasoningGraph
  -> decision
  -> citation-bound explanation
```

Automated extraction is treated as untrusted source assistance. Policy logic,
evaluation, and the explanation bound to an evaluation trace are deterministic;
no model resolves policy logic or determines an outcome.

Certified institutional context is currently retained alongside this path as
temporal explanation. The target path may consume a named context type only
when a future signed release explicitly authorises that effect.

## Proven In The Current Prototype

The actual API path has demonstrated:

- a policy draft authored by one identity;
- rejection when that author attempted to approve the same draft;
- approval by a different identity;
- compilation and cryptographic signing of the resulting release;
- evaluation against that release;
- the same evaluator operating across curriculum and grant domains.
- an independently certified shadow-calibration suite compared with a signed
  release, recording both matches and a classified mismatch without changing an
  institutional record or decision.

This establishes that the domain-neutral mechanism and governance gate work
under the tested conditions.

The prototype also preserves certified institutional context as temporal
history: it can record why an authorised concession, appeal outcome, curriculum
applicability decision, or assessment accommodation affected a subject's
position, while retaining the original event when a later decision supersedes
or revokes it. Context is currently explanatory only; a later signed-release
integration is required before it can influence evaluation.

## Not Yet Proven

The prototype has not yet been validated against a real institution's complete,
messy policy corpus. In particular:

- extraction has not been verified against long, contradictory source material;
- source authority and supersession rules have not been tested in a live policy
  environment;
- administrators have not used the system without reading JSON;
- the subject experience is trace-based but does not yet have a complete
  institution-integrated entry point, notification flow, or casework portal;
- enterprise identity, records, retention, privacy, and operations remain to be
  integrated.

The project is therefore validated decision infrastructure, not yet a deployable
institutional product.

## Next Empirical Milestone

Select one bounded decision from a real institution. Obtain the authoritative
policy sources and representative evidence, then:

1. model the policy through the governed draft/release path;
2. establish citations and supersession rules;
3. independently certify a non-identifying shadow-calibration suite containing
   known cases, including edge cases and prior decisions;
4. compare its outputs with institutional decision owners;
5. record disagreements as model, evidence, or governance failures;
6. measure extraction correction burden and explanation usefulness.

Additional infrastructure should be justified by failures observed in this
exercise, not by hypothetical completeness.
