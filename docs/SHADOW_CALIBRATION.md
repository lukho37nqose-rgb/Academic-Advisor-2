# Outcome Calibration

Outcome calibration is a tenant-neutral, non-operative comparison between a
signed policy release and a small set of representative recorded outcomes. It
exists to test whether a policy model represents institutional practice before
the system is considered for operational use.

It is not a live decision service, a system-of-record import, or a way to
change a subject's institutional status.

## Staff Workflow

1. A policy author selects a tenant domain and a cryptographically verified,
   signed release.
2. The author prepares representative cases in the staff workspace using typed
   fields from the domain schema. The route accepts only a non-identifying case
   reference, a short purpose, the recorded outcome, its source reference, and
   the facts needed by the selected release.
3. The author labels the data basis as either synthetic or approved
   de-identified. De-identified cases require the institution's privacy approval
   reference before submission.
4. A different permitted person certifies that the cases and recorded outcome
   references are appropriate for comparison.
5. A permitted staff member runs the suite against the signed release. The
   system stores one immutable report and opens a finding for each mismatch.
6. A person other than the suite author classifies every mismatch as source
   data, policy model, evidence, or governance, with a recorded note.

The browser makes actions visible only to roles allowed to perform them. The
API and database enforce the same tenant, domain, role, immutable-history, and
separation-of-duties rules independently of the browser.

## Data Boundary

Do not enter names, student numbers, email addresses, identity numbers, or
other direct identifiers. A case reference is a local, non-identifying label
such as `progression_edge_03`, not an identifier from an institutional system.

The application prevents identity fields in the case reference and requires a
privacy approval reference for de-identified historical cases. It cannot
reliably recognise every sensitive value that a person might type into a free
text fact or description. Institutions must therefore provide approved input
guidance, role training, and their own privacy review before real cases are
used.

## What Is Immutable

- The submitted case set and its canonical input hash.
- Certification identity, time, and note.
- The single report created by a completed run, including report hash, evaluated
  case results, input hashes, and trace hashes.
- The event history for submission, certification, and completion.

Findings retain their evidence and can move only from `OPEN` to `RESOLVED`.
Their independent resolution is an explanation of a mismatch, not a mutation of
the policy release or calibration evidence.

## First Case Study

UCT may be the first candidate case study because it is locally accessible to
the project team. It is not encoded as a tenant, a policy schema, an identity
provider, or a required workflow. Every institution supplies its own bounded
domain, authoritative sources, privacy approval, identity configuration, and
governance owners.
