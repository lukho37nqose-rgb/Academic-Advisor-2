"""Validate a bounded, non-operative institutional pilot before data intake.

This is deliberately a local assurance tool. It records no source bytes,
personal identifiers, transcript facts, or institutional decisions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field, field_validator, model_validator


PilotMode = Literal["LOCAL_REHEARSAL", "INSTITUTIONAL_SHADOW"]
SourceKind = Literal["POLICY_HANDBOOK", "POLICY_AMENDMENT", "TRANSCRIPT", "RECORDED_OUTCOME"]
DataBasis = Literal["PUBLIC_POLICY", "CONSENTED_SUBJECT_OWNED", "APPROVED_DEIDENTIFIED"]
PilotOwnerRole = Literal[
    "policy_owner",
    "release_approver",
    "identity_owner",
    "privacy_security_lead",
    "system_owner",
    "student_support_lead",
    "appeals_owner",
    "deployment_owner",
]
PlanStatus = Literal["NOT_REQUESTED", "REQUESTED", "PROVIDED", "APPROVED_DEFERRED", "NOT_APPLICABLE"]
IntegrationType = Literal["NONE", "MANUAL_MINIMISED_EXPORT", "CSV_EXPORT", "READ_ONLY_API", "WRITE_BACK"]
OperationalControlId = Literal[
    "retention_schedule",
    "object_immutability",
    "backup_restore_test",
    "incident_contact",
    "accessibility_route",
    "security_review",
    "malware_scanning",
    "monitoring_owner",
]


class PilotSource(BaseModel):
    reference: str = Field(min_length=5, max_length=500)
    kind: SourceKind
    authoritative: bool
    effective_period_confirmed: bool = False
    version_confirmed: bool = False


class PilotDataBoundary(BaseModel):
    reference: str = Field(min_length=5, max_length=500)
    basis: DataBasis
    contains_direct_identifiers: bool = False
    storage_boundary: Literal["LOCAL_ONLY", "TENANT_CONTROLLED"]
    approval_reference: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_appropriate_basis(self) -> "PilotDataBoundary":
        if self.basis == "CONSENTED_SUBJECT_OWNED" and not self.approval_reference:
            raise ValueError("Consented subject-owned material requires a consent reference.")
        if self.basis == "APPROVED_DEIDENTIFIED" and not self.approval_reference:
            raise ValueError("Approved de-identified material requires a privacy approval reference.")
        if self.contains_direct_identifiers and self.basis == "PUBLIC_POLICY":
            raise ValueError("Public policy material cannot contain direct identifiers.")
        if self.contains_direct_identifiers and self.basis == "APPROVED_DEIDENTIFIED":
            raise ValueError("Approved de-identified material cannot contain direct identifiers.")
        return self


class PilotOwner(BaseModel):
    role: PilotOwnerRole
    name_or_office: str | None = Field(default=None, max_length=240)
    confirmed: bool = False
    note: str = Field(min_length=5, max_length=1000)

    @model_validator(mode="after")
    def require_named_confirmed_owner(self) -> "PilotOwner":
        if self.confirmed and not (self.name_or_office or "").strip():
            raise ValueError("A confirmed pilot owner requires a named person, office, or group.")
        return self


class PilotIdentityPlan(BaseModel):
    status: PlanStatus = "NOT_REQUESTED"
    issuer: str | None = Field(default=None, max_length=500)
    audience: str | None = Field(default=None, max_length=500)
    jwks_url: str | None = Field(default=None, max_length=500)
    tenant_claim: str | None = Field(default=None, max_length=120)
    role_claim: str | None = Field(default=None, max_length=120)
    domain_claim: str | None = Field(default=None, max_length=120)
    subject_id_claim: str | None = Field(default=None, max_length=120)
    test_identities_count: int = Field(default=0, ge=0, le=100)

    @model_validator(mode="after")
    def require_oidc_fields_when_provided(self) -> "PilotIdentityPlan":
        if self.status == "PROVIDED":
            missing = [
                name for name in (
                    "issuer",
                    "audience",
                    "jwks_url",
                    "tenant_claim",
                    "role_claim",
                    "domain_claim",
                    "subject_id_claim",
                )
                if not getattr(self, name)
            ]
            if missing:
                raise ValueError(f"Provided identity plan is missing: {', '.join(missing)}.")
        return self


class PilotDeploymentPlan(BaseModel):
    hosting_boundary: Literal["LOCAL_ONLY", "INSTITUTION_APPROVED_NON_PRODUCTION", "CACISA_SYNTHETIC_DEMO"] = "LOCAL_ONLY"
    aws_account_status: PlanStatus = "NOT_APPLICABLE"
    terraform_state_status: PlanStatus = "NOT_APPLICABLE"
    database_boundary: Literal["LOCAL_SQLITE", "MANAGED_POSTGRES", "NOT_ASSIGNED"] = "LOCAL_SQLITE"
    object_storage_boundary: Literal["LOCAL_ONLY", "PRIVATE_OBJECT_STORE", "NOT_ASSIGNED"] = "LOCAL_ONLY"
    dns_tls_status: PlanStatus = "NOT_APPLICABLE"
    secrets_management_status: PlanStatus = "NOT_APPLICABLE"
    note: str = Field(default="Local rehearsal only.", max_length=1000)


class PilotOperationalControl(BaseModel):
    id: OperationalControlId
    status: PlanStatus
    owner_reference: str | None = Field(default=None, max_length=240)
    approval_reference: str | None = Field(default=None, max_length=500)
    note: str = Field(min_length=5, max_length=1000)


class PilotIntegrationPlan(BaseModel):
    system_name: str = Field(min_length=2, max_length=160)
    integration_type: IntegrationType
    status: PlanStatus = "NOT_REQUESTED"
    owner_reference: str | None = Field(default=None, max_length=240)
    schema_or_export_reference: str | None = Field(default=None, max_length=500)
    note: str = Field(min_length=5, max_length=1000)

    @model_validator(mode="after")
    def reject_write_back_for_shadow_pilot(self) -> "PilotIntegrationPlan":
        if self.integration_type == "WRITE_BACK":
            raise ValueError("The controlled pilot preflight does not permit write-back integrations.")
        return self


_PILOT_GATE_IDS = Literal[
    "bounded_decision",
    "non_operative_use",
    "policy_versioning",
    "source_provenance",
    "transcript_minimisation",
    "human_review_route",
    "expected_cases",
    "no_repository_storage",
]
_REQUIRED_GATE_IDS: frozenset[str] = frozenset(get_args(_PILOT_GATE_IDS))


class PilotGate(BaseModel):
    id: _PILOT_GATE_IDS  # type: ignore[valid-type]
    accepted: bool
    note: str = Field(min_length=5, max_length=1000)


class PilotManifest(BaseModel):
    format_version: Literal["1.0"] = "1.0"
    mode: PilotMode
    institution_name: str = Field(min_length=2, max_length=160)
    faculty_or_unit: str = Field(min_length=2, max_length=160)
    decision_name: str = Field(min_length=8, max_length=240)
    decision_statement: str = Field(min_length=30, max_length=2000)
    out_of_scope: list[str] = Field(min_length=1, max_length=20)
    sources: list[PilotSource] = Field(min_length=1, max_length=20)
    data_boundaries: list[PilotDataBoundary] = Field(min_length=1, max_length=20)
    gates: list[PilotGate] = Field(min_length=8, max_length=8)
    owners: list[PilotOwner] = Field(default_factory=list, max_length=20)
    identity_plan: PilotIdentityPlan = Field(default_factory=PilotIdentityPlan)
    deployment_plan: PilotDeploymentPlan = Field(default_factory=PilotDeploymentPlan)
    operational_controls: list[PilotOperationalControl] = Field(default_factory=list, max_length=20)
    integrations: list[PilotIntegrationPlan] = Field(default_factory=list, max_length=20)
    external_ocr_enabled: bool = False
    external_ai_enabled: bool = False
    external_processing_approval_reference: str | None = Field(default=None, max_length=500)

    @field_validator("institution_name", "faculty_or_unit", "decision_name", "decision_statement")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Pilot manifest text cannot be blank.")
        return value

    @model_validator(mode="after")
    def enforce_non_operative_boundary(self) -> "PilotManifest":
        provided_gate_ids = {gate.id for gate in self.gates}
        if provided_gate_ids != _REQUIRED_GATE_IDS:
            raise ValueError("The pilot manifest must declare every required preflight gate exactly once.")
        if self.mode == "LOCAL_REHEARSAL":
            if self.external_ocr_enabled or self.external_ai_enabled:
                raise ValueError("Local rehearsal cannot enable external OCR or AI processing.")
            if any(boundary.storage_boundary != "LOCAL_ONLY" for boundary in self.data_boundaries):
                raise ValueError("Local rehearsal material must stay local and outside tenant storage.")
        return self


class PilotPreflightReport(BaseModel):
    mode: PilotMode
    ready: bool
    blockers: list[str]
    warnings: list[str]
    decision_name: str
    source_count: int
    data_boundary_count: int
    confirmed_owner_count: int
    operational_control_count: int
    integration_count: int


def _contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return "REPLACE_" in value
    if isinstance(value, dict):
        return any(_contains_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_placeholder(item) for item in value)
    return False


def assess_manifest(manifest: PilotManifest) -> PilotPreflightReport:
    blockers: list[str] = []
    warnings: list[str] = []
    gates = {gate.id: gate for gate in manifest.gates}
    for gate_id, gate in gates.items():
        if not gate.accepted:
            blockers.append(f"{gate_id}: {gate.note}")

    if "REPLACE_" in manifest.decision_name or "REPLACE_" in manifest.decision_statement:
        blockers.append("The bounded decision has not been completed in the pilot manifest.")
    if manifest.mode == "INSTITUTIONAL_SHADOW" and _contains_placeholder(manifest.model_dump(mode="json")):
        blockers.append("The institutional shadow manifest still contains REPLACE_ placeholders.")

    policy_sources = [source for source in manifest.sources if source.kind in {"POLICY_HANDBOOK", "POLICY_AMENDMENT"}]
    if not policy_sources:
        blockers.append("At least one policy handbook or amendment source is required.")
    for source in policy_sources:
        if "REPLACE_" in source.reference:
            blockers.append("A policy source reference has not been completed in the pilot manifest.")
        if not source.authoritative:
            blockers.append(f"{source.reference}: policy source is not confirmed authoritative.")
        if not source.version_confirmed or not source.effective_period_confirmed:
            blockers.append(f"{source.reference}: policy version and effective period must be confirmed.")

    has_transcript = any(source.kind == "TRANSCRIPT" for source in manifest.sources)
    if has_transcript and not any(boundary.basis == "CONSENTED_SUBJECT_OWNED" for boundary in manifest.data_boundaries):
        blockers.append("A transcript requires a consented subject-owned or approved institutional data boundary.")

    if manifest.mode == "INSTITUTIONAL_SHADOW":
        required_roles: set[PilotOwnerRole] = {
            "policy_owner",
            "release_approver",
            "identity_owner",
            "privacy_security_lead",
            "system_owner",
            "student_support_lead",
            "appeals_owner",
            "deployment_owner",
        }
        confirmed_roles = {owner.role for owner in manifest.owners if owner.confirmed}
        missing_roles = sorted(required_roles - confirmed_roles)
        if missing_roles:
            blockers.append(f"Missing confirmed institutional owners: {', '.join(missing_roles)}.")
        if manifest.identity_plan.status != "PROVIDED" or manifest.identity_plan.test_identities_count < 3:
            blockers.append("Institutional shadow mode requires provided OIDC/JWKS details and at least three test identities.")
        deployment = manifest.deployment_plan
        if deployment.hosting_boundary != "INSTITUTION_APPROVED_NON_PRODUCTION":
            blockers.append("Institutional shadow mode requires an institution-approved non-production hosting boundary.")
        if deployment.database_boundary != "MANAGED_POSTGRES":
            blockers.append("Institutional shadow mode requires managed PostgreSQL, not local SQLite.")
        if deployment.object_storage_boundary != "PRIVATE_OBJECT_STORE":
            blockers.append("Institutional shadow mode requires private object storage for source material.")
        for field_name, label in (
            ("aws_account_status", "AWS/account ownership"),
            ("terraform_state_status", "Terraform remote state"),
            ("dns_tls_status", "DNS/TLS route"),
            ("secrets_management_status", "secrets management"),
        ):
            if getattr(deployment, field_name) != "PROVIDED":
                blockers.append(f"Institutional shadow mode requires provided {label}.")

        required_controls: set[OperationalControlId] = {
            "retention_schedule",
            "object_immutability",
            "backup_restore_test",
            "incident_contact",
            "accessibility_route",
            "security_review",
            "malware_scanning",
            "monitoring_owner",
        }
        controls = {control.id: control for control in manifest.operational_controls}
        for control_id in sorted(required_controls):
            control = controls.get(control_id)
            if control is None or control.status not in {"PROVIDED", "APPROVED_DEFERRED"}:
                blockers.append(f"Operational control is not approved: {control_id}.")
            elif control.status == "APPROVED_DEFERRED":
                warnings.append(f"Operational control approved as deferred: {control_id}.")
        if (manifest.external_ai_enabled or manifest.external_ocr_enabled) and not manifest.external_processing_approval_reference:
            blockers.append("External OCR or AI processing requires an institutional approval reference.")
        if not manifest.integrations:
            warnings.append("No system-of-record integration is declared; use only manual minimised evidence extracts.")
    else:
        warnings.append("Local rehearsal is not a UCT pilot, institutional decision, or evidence of policy approval.")

    return PilotPreflightReport(
        mode=manifest.mode,
        ready=not blockers,
        blockers=blockers,
        warnings=warnings,
        decision_name=manifest.decision_name,
        source_count=len(manifest.sources),
        data_boundary_count=len(manifest.data_boundaries),
        confirmed_owner_count=len([owner for owner in manifest.owners if owner.confirmed]),
        operational_control_count=len(manifest.operational_controls),
        integration_count=len(manifest.integrations),
    )


def load_manifest(path: Path) -> PilotManifest:
    return PilotManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a non-operative institutional pilot manifest.")
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    report = assess_manifest(load_manifest(args.manifest))
    print(json.dumps(report.model_dump(), indent=2, sort_keys=True))
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
