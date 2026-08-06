# UCT Humanities Local Rehearsal

This directory is a preparation area for a **local, non-operative rehearsal**.
It is not a UCT tenant, an approved pilot environment, or a claim that any UCT
rule has been interpreted correctly.

Do not commit a handbook, transcript, screenshot, exported record, generated
report, or a completed manifest here. The local `.gitignore` permits only this
guide and the blank manifest templates.

## Before using a real document

1. Choose one bounded decision. Do not begin with a whole degree audit.
2. Confirm the handbook edition, its effective dates, amendments, and the
   policy passages that answer that one question.
3. Treat a personally held transcript as consented, local test material only.
   Minimise it to the specific completed courses, results, credits, or dates
   required for the test; do not put it into Git, a public demo, or an external
   OCR/AI service.
4. Complete a local copy of `pilot_manifest.template.json` outside the
   repository, then run:

```powershell
python -m app.sdk.pilot_preflight --manifest C:\secure\path\pilot_manifest.json
```

5. A passing preflight permits only a local rehearsal. It does not permit
   uploading personal material to a shared environment or communicating an
   outcome as a UCT decision.

## Before a UCT-controlled shadow pilot

Use `institutional_shadow_manifest.template.json` only after UCT is willing to
discuss a tenant-controlled, non-production rehearsal. It turns the remaining
dependencies into named fields:

- policy owner and independent release approver;
- ICTS identity owner, OIDC/JWKS details, role claims, and test identities;
- non-production hosting boundary, PostgreSQL, private object storage, DNS/TLS,
  Terraform state, and secrets management;
- privacy, retention, Object Lock or equivalent immutability, malware scanning,
  backup restoration, incident route, monitoring, and accessibility route;
- PeopleSoft or Amathuba export shape only where the bounded decision actually
  needs those records.

Complete a copy outside the repository, then run:

```powershell
python -m app.sdk.pilot_preflight --manifest C:\secure\path\institutional_shadow_manifest.json
```

A passing institutional-shadow preflight still does not authorise operative
decisions or write-back. It means the non-operative pilot has named owners,
approved boundaries, and enough environment detail to run safely.

## Suggested first question

Prefer a question that can be answered from a small, cited rule set and a
minimal set of transcript facts, such as whether a stated prerequisite or
progression condition appears satisfied under one named handbook edition.

Keep concessions, appeals, accommodation, registration permission, degree
completion, and any adverse or consequential outcome out of the first rehearsal
unless an authorised institutional owner later includes them.
