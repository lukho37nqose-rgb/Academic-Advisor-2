# Real Institutional Pilot Readiness

For a first proposed institutional case study, apply the additional controls in
[UCT_PILOT_CHARTER.md](UCT_PILOT_CHARTER.md) and
[UCT_THREAT_MODEL.md](UCT_THREAT_MODEL.md) when UCT is the candidate. Those
documents do not claim UCT approval or affiliation; they define the material
and institutional sign-off required before a real source or record is used.
The controls are tenant-neutral and must be adapted for every future
institution.

The next phase is not a broader demo. It is a bounded test of whether the IRE
can represent one real institutional decision faithfully and explain it to the
people affected by it.

## Pre-Authorisation Rehearsal

The repository now includes a fully synthetic rehearsal pack under
[`pilot/synthetic/`](../pilot/synthetic/). It runs a fictional policy and
fictional subject facts through the same compiler and evaluator used for a
release. It proves the expected approval, threshold failure, missing-evidence
failure, and human-review routing paths, and retains canonical SHA-256 evidence
for each case.

This is useful for engineering regression control and a dry-run of the pilot
method. The staff workspace also supports an independently certified
shadow-calibration suite for the same purpose without requiring an institution
to prepare JSON or write code. It is not evidence that any real policy has been
modelled correctly. A real corpus and historical outcomes remain institutional
inputs, subject to the controls below.

## Institutional Inputs Required

1. A bounded decision: for example, one programme progression determination or
   one grant eligibility decision.
2. A named policy owner and a separate release approver.
3. The authoritative policy corpus, including amendments, effective dates,
   superseded versions, and source citations.
4. A privacy-approved set of synthetic representative cases or de-identified
   historic decisions, including difficult and disputed cases. The calibration
   route must never include direct subject identifiers.
5. A written definition of the subject, tenant, and domain access boundaries.
6. An OIDC application registration that supplies an issuer, audience, JWKS URL,
   and claims for tenant, role, and domain assignments.

## Large Document Acceptance Criteria

Before a multi-hundred-page handbook enters the release workflow, the pilot must
demonstrate that the ingestion design can:

- retain the original immutable object and SHA-256 hash;
- identify the authoritative edition and effective period;
- preserve page- or section-level provenance for every extracted claim;
- resume safely after partial extraction or worker failure;
- present proposed rules and their source passages for human correction;
- distinguish a citation correction from a policy change;
- keep unapproved extraction output out of the live release path.

The current text adapter is intentionally not that pipeline. It remains suitable
only for small reference evidence used to exercise the deterministic runtime.

## Pilot Exit Criteria

The pilot is successful only when the policy owner can reproduce a sample of
known decisions using a signed release, explain each outcome through the stored
evidence, claims, facts, and rule citations, and identify every disagreement as
either a source-data problem, policy-model problem, or governance decision.
The comparison must be recorded as a shadow-calibration report before any
operative use is considered.
