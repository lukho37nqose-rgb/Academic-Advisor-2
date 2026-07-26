"""Narrow adapter for an institution-approved OCR service.

OCR output is deliberately returned as untrusted page candidates. This module
does not write handbook pages, drafts, or releases.
"""

import json
import os
from typing import Any

import httpx
from pydantic import BaseModel, Field, field_validator


class OCRProviderUnavailableError(RuntimeError):
    """Raised when no institution-approved OCR service is configured."""


class OCRProviderResponseError(ValueError):
    """Raised when an OCR response cannot cover the requested source pages."""


class OCRPageCandidate(BaseModel):
    page_number: int = Field(gt=0)
    text: str = Field(min_length=1)
    provider_reference: str | None = Field(default=None, max_length=512)

    @field_validator("text")
    @classmethod
    def trim_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("OCR page text cannot be blank.")
        return trimmed


class OCRProviderResponse(BaseModel):
    pages: list[OCRPageCandidate]


def _provider_url() -> str:
    url = os.environ.get("OCR_PROVIDER_URL", "").strip()
    if not url:
        raise OCRProviderUnavailableError("No OCR provider has been configured for this institution.")
    return url


def is_configured() -> bool:
    return bool(os.environ.get("OCR_PROVIDER_URL", "").strip())


def provider_name() -> str:
    return os.environ.get("OCR_PROVIDER_NAME", "institution_ocr").strip() or "institution_ocr"


def _timeout_seconds() -> float:
    raw_value = os.environ.get("OCR_PROVIDER_TIMEOUT_SECONDS", "120")
    try:
        timeout = float(raw_value)
    except ValueError as exc:
        raise OCRProviderUnavailableError("OCR_PROVIDER_TIMEOUT_SECONDS must be numeric.") from exc
    if timeout < 10 or timeout > 600:
        raise OCRProviderUnavailableError("OCR_PROVIDER_TIMEOUT_SECONDS must be between 10 and 600 seconds.")
    return timeout


async def extract_page_candidates(
    source_file: Any,
    *,
    file_name: str,
    expected_pages: list[int],
) -> list[OCRPageCandidate]:
    """Requests candidate text for exactly the scanned handbook pages requested."""
    source_file.seek(0)
    headers: dict[str, str] = {}
    api_key = os.environ.get("OCR_PROVIDER_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=_timeout_seconds()) as client:
            response = await client.post(
                _provider_url(),
                headers=headers,
                data={"page_numbers": json.dumps(expected_pages)},
                files={"file": (file_name, source_file, "application/pdf")},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise OCRProviderUnavailableError("The configured OCR provider could not process this handbook source.") from exc

    try:
        parsed = OCRProviderResponse.model_validate(response.json())
    except (ValueError, TypeError) as exc:
        raise OCRProviderResponseError("The OCR provider returned an invalid review payload.") from exc

    candidates_by_page: dict[int, OCRPageCandidate] = {}
    for candidate in parsed.pages:
        if candidate.page_number in candidates_by_page:
            raise OCRProviderResponseError("The OCR provider returned duplicate page candidates.")
        candidates_by_page[candidate.page_number] = candidate
    if set(candidates_by_page) != set(expected_pages):
        raise OCRProviderResponseError("The OCR provider did not return a candidate for every scanned page.")
    return [candidates_by_page[page_number] for page_number in expected_pages]
