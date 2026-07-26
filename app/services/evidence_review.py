"""Governed evidence-to-fact proposals for deterministic evaluation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


EvidenceFactProposalAction = Literal["ACCEPT", "REJECT"]


class EvidenceFactProposalInput(BaseModel):
    """A staff-recorded candidate fact that must cite preserved evidence."""

    domain_id: str = Field(min_length=1, max_length=160)
    evidence_id: str = Field(min_length=1, max_length=160)
    target_path: str = Field(min_length=1, max_length=240)
    asserted_value: Any
    source_quote: str = Field(min_length=3, max_length=4000)
    source_locator: str | None = Field(default=None, max_length=500)

    @field_validator("domain_id", "evidence_id", "target_path", "source_quote")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Evidence fact proposal values cannot be blank.")
        return trimmed

    @field_validator("source_locator")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None


class EvidenceFactProposalAttestationRequest(BaseModel):
    domain_id: str = Field(min_length=1, max_length=160)
    action: EvidenceFactProposalAction
    note: str = Field(min_length=10, max_length=4000)

    @field_validator("domain_id", "note")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Evidence fact review values cannot be blank.")
        return trimmed


def validate_fact_value(value: Any, schema_type: str) -> Any:
    """Validate a reviewer-supplied value against the selected domain fact type."""

    if schema_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("This fact requires a numeric value.")
        return value
    if schema_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError("This fact requires a yes/no value.")
        return value
    if schema_type == "string":
        if not isinstance(value, str) or not value.strip():
            raise ValueError("This fact requires a non-empty text value.")
        return value.strip()
    raise ValueError("This domain fact has an unsupported schema type.")
