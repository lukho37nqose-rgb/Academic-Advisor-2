# Humanities Local Rehearsal

This guide prepares a first, consented local test using a Humanities handbook
and a personally held transcript. It is not an institutional integration or an
operative academic process.

## Goal

Test one small policy question end to end:

1. preserve a handbook edition and its citations;
2. represent only the required transcript facts;
3. create a reviewed, signed policy release;
4. compare expected positions through shadow calibration; and
5. show a citation-bound explanation or `NEEDS_MANUAL_REVIEW`.

Do not begin with full degree completion, registration permission, exclusion,
concessions, appeals, or a claim that the result is UCT's decision.

## Local handling rule

Keep the original handbook and transcript outside Git. Do not upload either to
an external OCR, AI, public demo, or shared cloud environment. The local
rehearsal is limited to the minimum facts needed for one question and does not
use a UCT tenant, SSO account, PeopleSoft connection, or outbound workflow.

## Procedure

1. Make a local copy of the manifest and decision dossier templates from
   [`pilot/uct_humanities/`](../pilot/uct_humanities/).
2. Confirm the handbook edition, effective period, relevant sections, and any
   amendment. If that cannot be established, stop and model the question as
   `NEEDS_MANUAL_REVIEW`.
3. Choose one question with a short path from rule to evidence. A named
   prerequisite is safer than a broad progression or graduation determination.
4. Create three non-identifying calibration cases: satisfied, not satisfied,
   and missing/exception. The third must remain manual review.
5. Run the preflight. It must report `ready: true` for **local rehearsal** only:

```powershell
python -m app.sdk.pilot_preflight --manifest C:\secure\path\humanities_manifest.json
```

6. Build the policy through the staff workflow, have a different identity
   approve and sign it, then enter minimal transcript facts as cited fact
   proposals. A different authorised identity accepts each fact.
7. Run a shadow-calibration suite. Record every mismatch; do not adjust an
   expected result until it has been classified as a source, policy, evidence,
   or governance issue.
8. Inspect the subject explanation and citation trail. Confirm it states record
   currency and routes ambiguity or exception to human review.

## Stop immediately when

- the handbook version or applicable cohort is unclear;
- a needed exception exists only in informal memory or unverified messages;
- the transcript contains more data than the question needs;
- the expected outcome cannot be independently justified;
- a result could be mistaken for an operative UCT decision; or
- the accessible human route is unclear.

The output of a successful rehearsal is a calibration report and a list of
open modelling questions. It is not a student-facing result or UCT evidence of
approval.
