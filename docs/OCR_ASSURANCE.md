# OCR Assurance Baseline

OCR is an optional transcription service at an untrusted boundary. It never
decides a subject's position, creates a policy rule, publishes a release, or
replaces the accessible source supplied by an institution.

## Delivered safeguards

1. **Provider-neutral structured contract.** Providers can return ordered text
   blocks, bounding boxes, table cells, quality signals, and a model version.
   The engine stores that structure as a proposal; it does not interpret it as
   policy.
2. **Page triage.** Selectable-text pages bypass external OCR. Blank/image-only
   pages are marked `SCANNED_OR_IMAGE_ONLY` and prioritised for review.
3. **Minimum disclosure.** The worker hash-verifies the original source, then
   sends only the requested scanned pages in temporary batches. The source PDF
   itself remains in tenant-controlled storage.
4. **Bounded work.** `OCR_MAX_PAGES_PER_JOB` and `OCR_MAX_PAGES_PER_REQUEST`
   bound cost and provider exposure. Durable jobs have tenant-scoped leases and
   dead-letter behaviour.
5. **Human review.** Every proposed page requires accept, correct, or reject.
   Pages with tables, handwriting, poor quality, digits, or likely policy terms
   are prioritised; prioritisation never bypasses review.
6. **Provenance.** Each proposal records source-page hash, provider response
   hash, proposal hash, provider reference, provider/model version, and an
   append-only review history.
7. **External-processing gate.** A provider must use HTTPS and may be limited
   to approved hosts. It is disabled unless an institution explicitly enables
   processing and records an approval reference.

## Required before a real institution enables OCR

- Approve a named provider or an internally operated service, including data
  residency, retention/deletion, incident terms, network egress, and costs.
- Build a permissioned evaluation corpus from representative handbook pages,
  with reviewed ground truth. Measure transcription, reading order, headings,
  tables, course codes, dates, and rule-meaning errors separately.
- Agree written acceptance thresholds and sampling rules. High-impact passages
  such as prerequisites, credit values, progression, exclusion, and dates
  should remain mandatory human review regardless of confidence.
- Validate provider output against the structured contract and retain test
  fixtures for regressions. A new provider model version requires calibration,
  not silent replacement.
- Complete malware scanning and document-quality checks before enabling OCR.
  Current PDF signature and parser checks are useful but are not malware
  protection.

## Explicitly not delivered

- A named OCR vendor, self-hosted GPU deployment, or an external processor
  approved by UCT.
- Reliable table reconstruction, semantic cross-page rule extraction, or
  automatic rule authoring. The contract preserves any provider structure for
  review, but the engine does not infer policy from it.
- Real-document benchmark results. Those must be produced with institutional
  permission and retained as pilot assurance evidence.
