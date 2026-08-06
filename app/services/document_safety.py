"""Small, dependency-free safety checks for untrusted handbook sources.

These checks deliberately do not claim to replace malware scanning, document
forensics, or accessibility review. They catch the most common mismatch between
what an upload claims to be and what it actually is before it enters OCR.
"""


class UnsafeDocumentError(ValueError):
    """Raised when an upload cannot safely be treated as a PDF source."""


def require_pdf_signature(prefix: bytes) -> None:
    """Require the PDF file signature before accepting a purported PDF."""

    if not prefix.startswith(b"%PDF-"):
        raise UnsafeDocumentError(
            "This upload is not a readable PDF. Use a PDF source or the assisted transcription route."
        )
