"""
Domain-neutral governance contracts.

The runtime understands governance capabilities and risk tiers. Edge domain
configuration supplies institution-specific targets and field names.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.services.auth import Role


class MetadataFieldPolicy(BaseModel):
    name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    risk: Literal["low"] = "low"
    notes: str = Field(min_length=1)


class MetadataTargetPolicy(BaseModel):
    target_type: str = Field(min_length=1)
    label: str = Field(min_length=1)
    identifier_label: str = Field(min_length=1)
    fields: list[MetadataFieldPolicy] = Field(min_length=1)

    def get_field(self, field_name: str) -> MetadataFieldPolicy | None:
        return next((field for field in self.fields if field.name == field_name), None)


class DomainGovernancePolicy(BaseModel):
    metadata_quick_edits: list[MetadataTargetPolicy] = Field(default_factory=list)
    review_required_changes: list[str] = Field(default_factory=list)
    formal_governance_changes: list[str] = Field(default_factory=list)

    def get_target(self, target_type: str) -> MetadataTargetPolicy | None:
        return next(
            (target for target in self.metadata_quick_edits if target.target_type == target_type),
            None,
        )

    def get_quick_edit_field(
        self,
        target_type: str,
        field_name: str,
    ) -> MetadataFieldPolicy | None:
        target = self.get_target(target_type)
        return target.get_field(field_name) if target else None


ROLE_PERMISSION_MATRIX: list[dict[str, Any]] = [
    {
        "role": Role.STAFF_MEMBER.value,
        "label": "Staff member",
        "can_quick_edit": True,
        "can_author_structured_drafts": False,
        "can_approve_releases": False,
        "can_replay_audits": False,
        "can_manage_assistance_requests": True,
        "can_manage_decision_reviews": True,
        "can_resolve_policy_ambiguities": False,
        "scope": "Assigned-domain records, assistance, decision review, cited fact proposals, institutional context, and low-risk metadata. Cannot attest their own work or change policy.",
    },
    {
        "role": Role.POLICY_EDITOR.value,
        "label": "Policy editor",
        "can_quick_edit": False,
        "can_author_structured_drafts": True,
        "can_approve_releases": False,
        "can_replay_audits": False,
        "can_manage_assistance_requests": False,
        "can_manage_decision_reviews": False,
        "can_resolve_policy_ambiguities": False,
        "scope": "Policy drafts; cannot approve their own releases.",
    },
    {
        "role": Role.APPROVER.value,
        "label": "Approver",
        "can_quick_edit": False,
        "can_author_structured_drafts": False,
        "can_approve_releases": True,
        "can_replay_audits": False,
        "can_manage_assistance_requests": False,
        "can_manage_decision_reviews": False,
        "can_resolve_policy_ambiguities": True,
        "scope": "Independently accepts cited facts, certifies context, settles sourced interpretations, and publishes releases. The same identity cannot approve its own proposal, record, or draft.",
    },
    {
        "role": Role.AUDITOR.value,
        "label": "Auditor",
        "can_quick_edit": False,
        "can_author_structured_drafts": False,
        "can_approve_releases": False,
        "can_replay_audits": True,
        "can_manage_assistance_requests": False,
        "can_manage_decision_reviews": False,
        "can_resolve_policy_ambiguities": False,
        "scope": "Read-only reasoning and governance history.",
    },
    {
        "role": Role.TENANT_ADMIN.value,
        "label": "Tenant administrator",
        "can_quick_edit": True,
        "can_author_structured_drafts": True,
        "can_approve_releases": True,
        "can_replay_audits": True,
        "can_manage_assistance_requests": True,
        "can_manage_decision_reviews": True,
        "can_resolve_policy_ambiguities": True,
        "scope": "Monitored break-glass access across the tenant; decisions remain separately auditable.",
    },
]


def get_role_permission_matrix() -> list[dict[str, Any]]:
    return ROLE_PERMISSION_MATRIX
