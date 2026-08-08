"""Effective-time selection model for governed institutional positions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.core.models import Fact


class PositionSelectionConflictError(ValueError):
    """Raised when governed information would make a position ambiguous."""


class InstitutionalPositionFact(BaseModel):
    """A governed fact selected for a subject at an effective time."""

    id: str
    target_path: str
    resolved_value: Any
    final_confidence: float = Field(ge=0.0, le=1.0)
    governance_state: Literal["ACCEPTED"] = "ACCEPTED"
    fact_status: Literal["resolved", "needs_human_review"] = "resolved"
    supporting_claims: list[str] = Field(default_factory=list)
    source_authority: Literal["official_system", "institutional_working_record", "subject_submitted"]
    record_state: Literal["confirmed"] = "confirmed"
    source_system: str | None = None
    source_record_version: str | None = None
    source_as_of: datetime
    recorded_at: datetime | None = None
    accepted_at: datetime | None = None
    evidence_id: str
    proposal_id: str
    source_locator: str | None = None

    def to_fact(self) -> Fact:
        return Fact(
            id=self.id,
            target_path=self.target_path,
            resolved_value=self.resolved_value,
            final_confidence=self.final_confidence,
            status=self.fact_status,
            supporting_claims=self.supporting_claims,
            source_authority=self.source_authority,
            record_state=self.record_state,
            source_system=self.source_system,
            source_record_version=self.source_record_version,
            source_as_of=self.source_as_of,
            recorded_at=self.recorded_at,
            accepted_at=self.accepted_at,
        )


class InstitutionalPosition(BaseModel):
    """Governed information selected for one subject and effective instant."""

    tenant_id: str
    domain_id: str
    subject_id: str
    effective_at: datetime
    known_at: datetime
    facts: list[InstitutionalPositionFact] = Field(default_factory=list)
    omitted_counts: dict[str, int] = Field(default_factory=dict)
    context_kind: Literal["actual", "historical"] = "actual"

    @model_validator(mode="after")
    def validate_governed_facts(self) -> "InstitutionalPosition":
        paths: set[str] = set()
        for fact in self.facts:
            if fact.target_path in paths:
                raise PositionSelectionConflictError(
                    f"Multiple governed facts were selected for target path '{fact.target_path}'."
                )
            paths.add(fact.target_path)
        return self

    @property
    def position_id(self) -> str:
        return f"position:{self.tenant_id}:{self.domain_id}:{self.subject_id}:{self.effective_at.isoformat()}"

    def as_reasoning_facts(self) -> list[Fact]:
        return [fact.to_fact() for fact in self.facts]


class PositionFactChange(BaseModel):
    target_path: str
    prior_value: Any
    new_value: Any
    effective_at: datetime
    source_system: str | None = None
    source_record_version: str | None = None
    evidence_id: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def compare_positions(
    prior: InstitutionalPosition,
    later: InstitutionalPosition,
) -> list[PositionFactChange]:
    prior_by_path = {fact.target_path: fact for fact in prior.facts}
    changes: list[PositionFactChange] = []
    for fact in later.facts:
        previous = prior_by_path.get(fact.target_path)
        if previous is not None and previous.resolved_value == fact.resolved_value:
            continue
        changes.append(
            PositionFactChange(
                target_path=fact.target_path,
                prior_value=previous.resolved_value if previous else None,
                new_value=fact.resolved_value,
                effective_at=fact.source_as_of,
                source_system=fact.source_system,
                source_record_version=fact.source_record_version,
                evidence_id=fact.evidence_id,
            )
        )
    return changes
