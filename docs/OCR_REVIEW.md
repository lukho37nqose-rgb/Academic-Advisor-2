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

The OCR worker verifies the stored handbook SHA-256 before sending it to the configured provider. The provider must return exactly one non-empty candidate for each scanned page. Candidates are stored separately from handbook page text with a proposal hash and an append-only review event. `ACCEPT` and `CORRECT` are the only actions that write reviewed text to a handbook page; `REJECT` leaves the source page blank and the handbook outside the release path.

Run the worker outside the API process:

```powershell
python -m app.services.handbook_ocr_worker handbook_<id>
```

## Provider contract

Set `OCR_PROVIDER_URL` to an institution-approved HTTPS service. The engine sends a multipart `file` field containing the verified PDF and a `page_numbers` JSON form field. The service returns:

```json
{
  "pages": [
    {
      "page_number": 14,
      "text": "Selectable candidate text for this page.",
      "provider_reference": "optional-job-or-page-reference"
    }
  ]
}
```

Configure `OCR_PROVIDER_NAME`, `OCR_PROVIDER_API_KEY`, and `OCR_PROVIDER_TIMEOUT_SECONDS` as appropriate. The provider must be covered by the institution's data-processing, retention, residency, and accessibility commitments before it receives any source document. If no provider is configured or it fails to cover every scanned page, the handbook remains in manual review with an accessible-text or assisted-transcription route.
