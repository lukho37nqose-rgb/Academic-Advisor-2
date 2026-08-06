# Policy Applicability And Interpretation Governance

## Purpose

A deterministic evaluator is only trustworthy when it can establish both the
rule release it used and why that release governed the subject at that time.
This layer turns effective dates, transitional applicability, and unresolved
interpretations into explicit institutional records.

It is domain-neutral. An institution may use selectors such as `entry_year`,
`programme_type`, `jurisdiction`, or another approved policy-routing attribute.
Selectors are not a full subject profile and must not be used to insert
unnecessary personal data into a reasoning trace.

## Policy interpretation register

An ambiguity record contains:

- a citation to the source text;
- the precise interpretation question;
- at least two plausible readings;
- the person who raised it;
- a formal resolution and authoritative source reference; and
- an append-only event history.

An ambiguity names the policy facts it affects. It blocks a release only when
that release evaluates one of those facts. This prevents an unrelated
interpretation question from freezing harmless policy maintenance while still
preventing the system from replacing a relevant institutional interpretation
with an unstated developer or model assumption. Older ambiguity records with
no declared scope remain conservatively blocking until resolved. The person who
raised an ambiguity cannot resolve it. An `approver` or monitored `tenant_admin`
records the resolution; the same role may publish the release only when it is a
different identity from the draft author.

The register may be managed from the **Policy Register** interface. It never
compiles or changes a policy on its own.

## Effective periods and applicability

Every newly published release requires an `effective_from` date and may have
an inclusive `effective_until` date. It may also carry a set of applicability
criteria. For example, an institution can publish separate rules for
`entry_year = 2026` and `entry_year = 2027` without giving the evaluator any
institution-specific code.

The runtime rejects publication if another release in the same domain has both:

1. an overlapping effective period; and
2. an overlapping applicability context.

The evaluator requires an `as_of_date` for a scheduled release and rejects a
release outside its effective period. It also rejects missing or mismatched
applicability selectors. The accepted date and selectors are persisted in the
immutable `EvaluationContext`, so replay can show why the policy version was
eligible to govern that decision.

The release signature covers the policy payload, version, effective period,
applicability selectors, release identity, domain, and compiled rule-graph ID
together. Re-scoping a release therefore changes the signed material. New
releases also retain the signed envelope, hash, public-key snapshot, and key ID
so an auditor can verify it after the active signing key has rotated.

## Transition from legacy releases

Releases created before this capability have null effective-period fields and
remain evaluable for historical replay. They are not silently assigned new
dates. Institutions should issue a new signed release with explicit scheduling
before using a legacy release for new operative evaluations.

## Operational requirements

- The policy owner must define approved selector names and their source of
  truth before a pilot uses cohort or transitional routing.
- Institution-integrated callers must obtain selector values from the approved
  system of record and minimise them to the values needed for routing.
- Policy changes must close or supersede prior periods rather than altering an
  existing release.
- Production Postgres serialises governed changes for each domain with a
  transaction-scoped advisory lock. The release row, compiled graph, and draft
  status transition commit together while that lock is held. A concurrent writer
  receives a retryable conflict instead of silently publishing against stale
  state.
- Database roles, row-level security, and an independently controlled audit
  export remain deployment release gates for a shared multi-tenant service.
