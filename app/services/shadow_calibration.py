"""Tenant-neutral inputs for non-operative policy calibration."""

from __future__ import annotations

import datetime
import hashlib
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.sdk.pilot_rehearsal import GoldenCase, GoldenFact, PilotRehearsalSuite


CalibrationDecision = Literal["ELIGIBLE", "INELIGIBLE", "NEEDS_MANUAL_REVIEW"]
CalibrationDataBasis = Literal["SYNTHETIC", "APPROVED_DEIDENTIFIED"]


class ShadowCalibrationFactInput(BaseModel):
    target_path: str = Field(min_length=1, max_length=240)
    value: Any
    status: Literal["resolved", "needs_human_review"] = "resolved"

    @field_validator("target_path")
    @classmethod
    def trim_target_path(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("A calibration fact needs a policy field.")
        return trimmed


class ShadowCalibrationCaseInput(BaseModel):
    case_reference: str = Field(min_length=3, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    description: str = Field(min_length=5, max_length=1200)
    recorded_decision: CalibrationDecision
    recorded_outcome_reference: str = Field(min_length=5, max_length=500)
    facts: list[ShadowCalibrationFactInput] = Field(min_length=1, max_length=100)

    @field_validator("description", "recorded_outcome_reference")
    @classmethod
    def trim_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Calibration case details cannot be blank.")
        return trimmed

    @model_validator(mode="after")
    def require_unique_fact_paths(self) -> "ShadowCalibrationCaseInput":
        paths = [fact.target_path for fact in self.facts]
        if len(paths) != len(set(paths)):
            raise ValueError("Each calibration case may use a policy fact only once.")
        return self


class ShadowCalibrationSuiteInput(BaseModel):
    domain_id: str = Field(min_length=1, max_length=160)
    release_id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=10, max_length=2000)
    data_basis: CalibrationDataBasis
    privacy_approval_reference: str | None = Field(default=None, max_length=500)
    policy_as_of_date: datetime.date
    cases: list[ShadowCalibrationCaseInput] = Field(min_length=1, max_length=100)

    @field_validator("domain_id", "release_id", "name", "description")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Calibration suite values cannot be blank.")
        return trimmed

    @field_validator("privacy_approval_reference")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value else None

    @model_validator(mode="after")
    def require_non_identifying_case_references(self) -> "ShadowCalibrationSuiteInput":
        references = [case.case_reference for case in self.cases]
        if len(references) != len(set(references)):
            raise ValueError("Each calibration case needs a unique non-identifying reference.")
        if self.data_basis == "APPROVED_DEIDENTIFIED":
            if not self.privacy_approval_reference or len(self.privacy_approval_reference) < 8:
                raise ValueError(
                    "Approved de-identified calibration data requires a privacy approval reference."
                )
        return self


class ShadowCalibrationFindingResolution(BaseModel):
    classification: Literal["SOURCE_DATA", "POLICY_MODEL", "EVIDENCE", "GOVERNANCE"]
    note: str = Field(min_length=10, max_length=4000)

    @field_validator("note")
    @classmethod
    def trim_note(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("A mismatch resolution needs a note.")
        return trimmed


class ShadowCalibrationCertificationRequest(BaseModel):
    domain_id: str = Field(min_length=1, max_length=160)
    note: str = Field(min_length=10, max_length=4000)

    @field_validator("domain_id", "note")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Calibration certification values cannot be blank.")
        return trimmed


class ShadowCalibrationRunRequest(BaseModel):
    domain_id: str = Field(min_length=1, max_length=160)

    @field_validator("domain_id")
    @classmethod
    def trim_domain_id(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("A calibration run needs a decision domain.")
        return trimmed


class ShadowCalibrationFindingResolutionRequest(ShadowCalibrationFindingResolution):
    domain_id: str = Field(min_length=1, max_length=160)

    @field_validator("domain_id")
    @classmethod
    def trim_domain_id(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("A finding resolution needs a decision domain.")
        return trimmed


def validate_cases_against_domain_fields(
    cases: list[ShadowCalibrationCaseInput],
    fields: list[dict[str, str]],
) -> None:
    """Reject undeclared fields and values that do not match the domain schema."""
    field_types = {field["target_path"]: field["schema_type"] for field in fields}
    for case in cases:
        for fact in case.facts:
            schema_type = field_types.get(fact.target_path)
            if schema_type is None:
                raise ValueError(f"'{fact.target_path}' is not a declared fact for this decision domain.")
            if schema_type == "number" and (
                isinstance(fact.value, bool) or not isinstance(fact.value, (int, float))
            ):
                raise ValueError(f"'{fact.target_path}' requires a numeric calibration value.")
            if schema_type == "boolean" and not isinstance(fact.value, bool):
                raise ValueError(f"'{fact.target_path}' requires a yes/no calibration value.")
            if schema_type == "string" and (
                not isinstance(fact.value, str) or not fact.value.strip()
            ):
                raise ValueError(f"'{fact.target_path}' requires a non-empty text calibration value.")


def build_rehearsal_suite(
    *,
    suite_id: str,
    tenant_id: str,
    domain_id: str,
    release_id: str,
    release_version: str,
    policy_as_of_date: datetime.date,
    description: str,
    cases: list[dict[str, Any]],
    evaluation_timestamp: str,
) -> PilotRehearsalSuite:
    """Convert reviewed stored input into the existing deterministic rehearsal contract."""
    golden_cases: list[GoldenCase] = []
    for case in cases:
        case_identifier = case.get("case_id", case.get("id"))
        if not isinstance(case_identifier, str) or not case_identifier:
            raise ValueError("Stored calibration case has no stable identifier.")
        case_id = case_identifier
        golden_facts: list[GoldenFact] = []
        for fact in cast_facts(case["facts"]):
            fact_id = hashlib.sha256(
                f"{case_id}:{fact['target_path']}".encode("utf-8")
            ).hexdigest()[:24]
            golden_facts.append(
                GoldenFact(
                    id=f"cal_fact_{fact_id}",
                    target_path=fact["target_path"],
                    resolved_value=fact["value"],
                    final_confidence=1.0,
                    status=fact["status"],
                )
            )
        golden_cases.append(
            GoldenCase(
                id=case_id,
                description=str(case["description"]),
                subject_reference=f"shadow:{case['case_reference']}",
                facts=golden_facts,
                expected_decision=case["recorded_decision"],
            )
        )
    return PilotRehearsalSuite(
        suite_id=suite_id,
        description=description,
        release_id=release_id,
        tenant_id=tenant_id,
        domain_id=domain_id,
        release_version=release_version,
        policy_as_of_date=policy_as_of_date,
        evaluation_timestamp=evaluation_timestamp,
        cases=golden_cases,
    )


def cast_facts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("Stored calibration facts are not valid.")
    return value
