"""Validated, non-operative institutional context records for timeline use."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


InstitutionalContextEventType = Literal[
    "CONCESSION",
    "CURRICULUM_APPLICABILITY",
    "ASSESSMENT_ACCOMMODATION",
    "APPEAL_OUTCOME",
    "REGISTRATION_POSITION",
    "PROGRESSION_POSITION",
    "GRADUATION_POSITION",
    "OTHER",
]
InstitutionalContextVisibility = Literal["SUBJECT", "STAFF_ONLY"]
InstitutionalContextPredecessorRelationship = Literal["SUPERSEDES", "REVOKES"]
InstitutionalContextAttestationAction = Literal["CERTIFY", "REJECT"]


class InstitutionalContextEventInput(BaseModel):
    """A record of an already-authorised event; it cannot create an exception."""

    domain_id: str = Field(min_length=1, max_length=160)
    subject_id: str = Field(min_length=1, max_length=320)
    event_type: InstitutionalContextEventType
    title: str = Field(min_length=5, max_length=240)
    student_summary: str = Field(min_length=10, max_length=4000)
    institutional_effect: str = Field(min_length=10, max_length=4000)
    authority_name: str = Field(min_length=3, max_length=240)
    authority_reference: str = Field(min_length=3, max_length=500)
    source_reference: str = Field(min_length=3, max_length=1000)
    event_date: date
    effective_from: date
    effective_until: date | None = None
    visibility: InstitutionalContextVisibility = "SUBJECT"
    policy_release_id: str | None = Field(default=None, max_length=160)
    policy_citation: str | None = Field(default=None, max_length=2000)
    predecessor_event_id: str | None = Field(default=None, max_length=160)
    predecessor_relationship: InstitutionalContextPredecessorRelationship | None = None

    @field_validator(
        "domain_id",
        "subject_id",
        "title",
        "student_summary",
        "institutional_effect",
        "authority_name",
        "authority_reference",
        "source_reference",
    )
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Institutional context values cannot be blank.")
        return trimmed

    @field_validator(
        "policy_release_id",
        "policy_citation",
        "predecessor_event_id",
    )
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @model_validator(mode="after")
    def validate_timing_and_predecessor(self) -> "InstitutionalContextEventInput":
        if self.effective_until and self.effective_until < self.effective_from:
            raise ValueError("An institutional context event cannot end before it takes effect.")
        if bool(self.predecessor_event_id) != bool(self.predecessor_relationship):
            raise ValueError("A superseding or revoking event must name the earlier event it affects.")
        return self


class InstitutionalContextAttestationRequest(BaseModel):
    domain_id: str = Field(min_length=1, max_length=160)
    action: InstitutionalContextAttestationAction
    note: str = Field(min_length=10, max_length=4000)

    @field_validator("domain_id", "note")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Institutional context attestation values cannot be blank.")
        return trimmed
