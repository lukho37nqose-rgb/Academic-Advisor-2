"""Narrow adapter for an institution-approved OCR service.

OCR output is deliberately returned as untrusted page candidates. This module
does not write handbook pages, drafts, or releases.
"""

import json
import os
from hashlib import sha256
from typing import Any
from urllib.parse import urlparse

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
    blocks: list["OCRContentBlock"] = Field(default_factory=list)
    quality_signals: "OCRQualitySignals" = Field(default_factory=lambda: OCRQualitySignals())

    @field_validator("text")
    @classmethod
    def trim_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("OCR page text cannot be blank.")
        return trimmed


class OCRBoundingBox(BaseModel):
    x0: float = Field(ge=0)
    y0: float = Field(ge=0)
    x1: float = Field(gt=0)
    y1: float = Field(gt=0)


class OCRContentBlock(BaseModel):
    text: str = Field(min_length=1)
    block_type: str = Field(default="text", max_length=64)
    reading_order: int = Field(default=0, ge=0)
    bounding_box: OCRBoundingBox | None = None
    table_cells: list[list[str]] | None = None


class OCRQualitySignals(BaseModel):
    confidence: float | None = Field(default=None, ge=0, le=1)
    language: str | None = Field(default=None, max_length=32)
    contains_table: bool = False
    handwritten: bool = False
    low_quality_scan: bool = False
    continuation_from_previous_page: bool = False


class OCRProviderResponse(BaseModel):
    pages: list[OCRPageCandidate]
    provider_model_version: str | None = Field(default=None, max_length=256)


def _provider_url() -> str:
    url = os.environ.get("OCR_PROVIDER_URL", "").strip()
    if not url:
        raise OCRProviderUnavailableError("No OCR provider has been configured for this institution.")
    return url


def _external_processing_is_approved() -> bool:
    return (
        os.environ.get("IRE_ALLOW_EXTERNAL_OCR_PROCESSING", "false").strip().lower() == "true"
        and bool(os.environ.get("IRE_EXTERNAL_OCR_APPROVAL_REFERENCE", "").strip())
    )


def is_configured() -> bool:
    return bool(os.environ.get("OCR_PROVIDER_URL", "").strip()) and _external_processing_is_approved()


def provider_name() -> str:
    return os.environ.get("OCR_PROVIDER_NAME", "institution_ocr").strip() or "institution_ocr"


def provider_model_version() -> str | None:
    value = os.environ.get("OCR_PROVIDER_MODEL_VERSION", "").strip()
    return value or None


def _validate_provider_destination(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise OCRProviderUnavailableError("OCR_PROVIDER_URL must use HTTPS.")
    allowlist = {value.strip().lower() for value in os.environ.get("OCR_ALLOWED_PROVIDER_HOSTS", "").split(",") if value.strip()}
    if allowlist and parsed.hostname.lower() not in allowlist:
        raise OCRProviderUnavailableError("OCR provider host is not in OCR_ALLOWED_PROVIDER_HOSTS.")


def _timeout_seconds() -> float:
    raw_value = os.environ.get("OCR_PROVIDER_TIMEOUT_SECONDS", "120")
    try:
        timeout = float(raw_value)
    except ValueError as exc:
        raise OCRProviderUnavailableError("OCR_PROVIDER_TIMEOUT_SECONDS must be numeric.") from exc
    if timeout < 10 or timeout > 600:
        raise OCRProviderUnavailableError("OCR_PROVIDER_TIMEOUT_SECONDS must be between 10 and 600 seconds.")
    return timeout


def _bounded_page_limit(name: str, default: int, *, maximum: int) -> int:
    raw_value = os.environ.get(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise OCRProviderUnavailableError(f"{name} must be a whole number.") from exc
    if value < 1 or value > maximum:
        raise OCRProviderUnavailableError(f"{name} must be between 1 and {maximum}.")
    return value


def max_pages_per_job() -> int:
    return _bounded_page_limit("OCR_MAX_PAGES_PER_JOB", 250, maximum=2_000)


def max_pages_per_request() -> int:
    return _bounded_page_limit("OCR_MAX_PAGES_PER_REQUEST", 25, maximum=250)


async def extract_page_candidates(
    source_file: Any,
    *,
    file_name: str,
    expected_pages: list[int],
) -> tuple[list[OCRPageCandidate], str | None, str]:
    """Requests candidate text for exactly the scanned handbook pages requested."""
    if not _external_processing_is_approved():
        raise OCRProviderUnavailableError("External OCR processing has not been approved for this institution.")
    url = _provider_url()
    _validate_provider_destination(url)
    if not expected_pages:
        raise OCRProviderResponseError("OCR requires at least one requested page.")
    if len(expected_pages) > max_pages_per_request():
        raise OCRProviderResponseError("OCR request exceeds OCR_MAX_PAGES_PER_REQUEST.")
    source_file.seek(0)
    headers: dict[str, str] = {}
    api_key = os.environ.get("OCR_PROVIDER_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=_timeout_seconds()) as client:
            response = await client.post(
                url,
                headers=headers,
                data={"page_numbers": json.dumps(expected_pages)},
                files={"file": (file_name, source_file, "application/pdf")},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise OCRProviderUnavailableError("The configured OCR provider could not process this handbook source.") from exc

    try:
        response_payload = response.json()
        parsed = OCRProviderResponse.model_validate(response_payload)
    except (ValueError, TypeError) as exc:
        raise OCRProviderResponseError("The OCR provider returned an invalid review payload.") from exc

    candidates_by_page: dict[int, OCRPageCandidate] = {}
    for candidate in parsed.pages:
        if candidate.page_number in candidates_by_page:
            raise OCRProviderResponseError("The OCR provider returned duplicate page candidates.")
        candidates_by_page[candidate.page_number] = candidate
    if set(candidates_by_page) != set(expected_pages):
        raise OCRProviderResponseError("The OCR provider did not return a candidate for every scanned page.")
    response_hash = sha256(
        json.dumps(response_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return [candidates_by_page[page_number] for page_number in expected_pages], (parsed.provider_model_version or provider_model_version()), response_hash
