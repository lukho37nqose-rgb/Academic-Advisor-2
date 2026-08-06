from __future__ import annotations

import pytest

from app.services import ocr_provider


def test_external_ocr_requires_explicit_approval_reference(monkeypatch):
    monkeypatch.setenv("OCR_PROVIDER_URL", "https://ocr.example.test/process")
    monkeypatch.setenv("IRE_ALLOW_EXTERNAL_OCR_PROCESSING", "true")
    monkeypatch.delenv("IRE_EXTERNAL_OCR_APPROVAL_REFERENCE", raising=False)

    assert ocr_provider.is_configured() is False

    monkeypatch.setenv("IRE_EXTERNAL_OCR_APPROVAL_REFERENCE", "DPA-2026-001")
    assert ocr_provider.is_configured() is True


def test_ocr_page_limits_fail_closed(monkeypatch):
    monkeypatch.setenv("OCR_MAX_PAGES_PER_JOB", "0")
    with pytest.raises(ocr_provider.OCRProviderUnavailableError):
        ocr_provider.max_pages_per_job()

    monkeypatch.setenv("OCR_MAX_PAGES_PER_REQUEST", "251")
    with pytest.raises(ocr_provider.OCRProviderUnavailableError):
        ocr_provider.max_pages_per_request()


def test_structured_candidates_preserve_layout_and_quality_signals():
    candidate = ocr_provider.OCRPageCandidate.model_validate({
        "page_number": 4,
        "text": "BIO1010F requires MAT1000W.",
        "blocks": [{
            "text": "BIO1010F requires MAT1000W.",
            "block_type": "paragraph",
            "reading_order": 1,
            "bounding_box": {"x0": 20, "y0": 30, "x1": 400, "y1": 60},
        }],
        "quality_signals": {"confidence": 0.93, "contains_table": True},
    })

    assert candidate.blocks[0].reading_order == 1
    assert candidate.blocks[0].bounding_box is not None
    assert candidate.quality_signals.contains_table is True
