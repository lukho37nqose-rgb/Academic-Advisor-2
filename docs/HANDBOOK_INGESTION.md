# Handbook Ingestion

Handbook intake is deliberately a source-verification and review workflow, not an automatic rule-publishing feature.

## Lifecycle

```text
PDF upload -> SHA-256 verified object -> QUEUED
         -> external worker -> page checkpoints -> READY_FOR_REVIEW
                                      -> NEEDS_MANUAL_REVIEW (missing selectable text)
         -> human authors a draft -> separate approval -> signed release
```

The standard upload API accepts only PDFs and streams them through a spooled temporary file while enforcing `HANDBOOK_UPLOAD_MAX_BYTES` (250 MB by default). It records the filename, MIME type, size, SHA-256 hash, storage key, uploader, and domain. The HTTP request never extracts rules and cannot publish anything.

## Direct storage upload

When S3 is configured, the interface first requests a short-lived upload session. The browser then sends the source directly to a single, constrained staging key rather than through the API server. Completion checks the exact declared object size and MIME type, creates a one-time queued job, and returns control to the same extraction worker.

The worker reads the staged bytes, computes the authoritative SHA-256 hash, writes a content-addressed encrypted source object, and only then begins page extraction. A browser-supplied filename, MIME type, or upload response is never treated as proof of the source bytes.

The production bucket must allow CORS only for the institution's application origin, block public access, use bucket versioning and lifecycle cleanup for abandoned `handbook-staging/` objects, and restrict presigned uploads to the application's IAM role. Set `S3_BUCKET_NAME`, `S3_SERVER_SIDE_ENCRYPTION`, `HANDBOOK_DIRECT_UPLOAD_MAX_BYTES` (2 GB by default), and `HANDBOOK_UPLOAD_SESSION_TTL_SECONDS` (15 minutes by default). Without S3, the interface automatically uses the existing bounded API upload path.

The worker is started outside the API process:

```powershell
python -m app.services.handbook_worker handbook_<id>
```

It retrieves the immutable object, verifies its SHA-256 hash again, processes pages individually, and commits each page as a checkpoint. If it stops, rerunning it for the same handbook continues at the next unprocessed page. The worker marks a source `READY_FOR_REVIEW` only after all page checkpoints have been written and every page contains selectable text. An encrypted or corrupted document is marked `FAILED` with a bounded error message.

Authors, approvers, and auditors can inspect those checkpoints in the Handbook Intake screen. The API returns a bounded page slice rather than an entire source (`GET /api/v1/governance/handbooks/{handbook_id}/pages`), and the interface presents the filename and page number alongside each excerpt so a later rule citation stays tied to its source.

## Large and scanned documents

The worker spools source bytes to disk after 8 MB rather than retaining the entire handbook in process memory. Object storage remains the source of truth. Production deployments should run this worker from a durable queue with one job per source and metric/alert coverage for `FAILED` and long-running `EXTRACTING` jobs.

`pypdf` extracts embedded text. It does not perform OCR, table reconstruction, semantic rule extraction, or determine which source passage is authoritative. A scanned handbook may therefore have blank page text even though its source object and page count are valid. Any source with one or more pages lacking selectable text is marked `NEEDS_MANUAL_REVIEW`, never `READY_FOR_REVIEW`; it cannot produce a policy draft or release until an accessible text source or a reviewed OCR result is available. OCR and LLM-assisted rule proposals belong in a later, separately validated worker stage, with each proposal linked to page text and routed through the normal draft/review/release workflow.

The reviewed OCR stage is now available through the Handbook Intake screen and is documented in `docs/OCR_REVIEW.md`. It keeps provider text separate from source text until a named staff reviewer accepts or corrects the proposal for that page.

For sources larger than the configured HTTP upload limit, the next production extension is a direct-to-object-storage upload session. It must preserve the same hash, metadata, queue record, and review boundary.
