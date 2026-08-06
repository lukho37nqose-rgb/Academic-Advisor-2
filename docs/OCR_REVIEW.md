# Reviewed OCR

OCR is an accessibility and transcription aid, never a rule-authoring authority.

## Workflow

```text
Scanned handbook -> NEEDS_MANUAL_REVIEW
                 -> staff requests OCR -> OCR_QUEUED
                 -> external OCR worker -> OCR_REVIEW_REQUIRED
                 -> staff accepts, corrects, or rejects each page proposal
                 -> READY_FOR_REVIEW only when every page has reviewed text
                 -> normal draft, approval, and signed-release workflow
```

The OCR worker verifies the stored handbook SHA-256 before sending anything to a configured provider. It creates a temporary PDF containing only the scanned pages requested for OCR; the complete handbook remains in private storage. The provider must return exactly one non-empty candidate for each original page number. Candidates are stored separately from handbook page text with a source-page hash, provider-response hash, proposal hash, and append-only review event. `ACCEPT` and `CORRECT` are the only actions that write reviewed text to a handbook page; `REJECT` leaves the source page blank and the handbook outside the release path.

Run the worker outside the API process:

```powershell
python -m app.services.handbook_ocr_worker handbook_<id>
```

## Provider contract

Set `OCR_PROVIDER_URL` to an institution-approved HTTPS service. OCR remains disabled until both `IRE_ALLOW_EXTERNAL_OCR_PROCESSING=true` and a non-empty `IRE_EXTERNAL_OCR_APPROVAL_REFERENCE` are configured. The engine sends a multipart `file` containing only the relevant page subset and a `page_numbers` JSON form field containing the **original handbook page numbers**. `OCR_ALLOWED_PROVIDER_HOSTS` can restrict the endpoint to approved hosts. The service returns:

```json
{
  "pages": [
    {
      "page_number": 14,
      "text": "Selectable candidate text for this page.",
      "provider_reference": "optional-job-or-page-reference",
      "blocks": [{
        "text": "Selectable candidate text for this page.",
        "block_type": "paragraph",
        "reading_order": 1,
        "bounding_box": {"x0": 72, "y0": 100, "x1": 520, "y1": 140}
      }],
      "quality_signals": {
        "confidence": 0.98,
        "language": "en",
        "contains_table": false,
        "handwritten": false,
        "low_quality_scan": false,
        "continuation_from_previous_page": false
      }
    }
  ]
}
```

The optional top-level field `provider_model_version` is preserved with every proposal. Configure `OCR_PROVIDER_NAME`, `OCR_PROVIDER_API_KEY`, `OCR_PROVIDER_TIMEOUT_SECONDS`, `OCR_MAX_PAGES_PER_JOB`, and `OCR_MAX_PAGES_PER_REQUEST` as appropriate. The provider must be covered by the institution's data-processing, retention, residency, and accessibility commitments before it receives any source document. If no provider is configured or it fails to cover every scanned page, the handbook remains in manual review with an accessible-text or assisted-transcription route.
