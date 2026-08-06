import pytest

from app.services.document_safety import UnsafeDocumentError, require_pdf_signature


def test_pdf_signature_accepts_pdf_header():
    require_pdf_signature(b"%PDF-1.7\n")


def test_pdf_signature_rejects_mislabeled_content():
    with pytest.raises(UnsafeDocumentError, match="not a readable PDF"):
        require_pdf_signature(b"<html>")
