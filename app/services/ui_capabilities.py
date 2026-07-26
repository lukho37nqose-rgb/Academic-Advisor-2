"""Server-issued workspace capabilities for the reference client.

The browser may use this response to decide which workspace to render, but it
is not an authorisation mechanism. Every API route continues to enforce role,
tenant, domain, and (where relevant) subject ownership independently.
"""

from typing import Literal, TypedDict

from app.services.auth import Role, UserIdentity


WorkspaceExperience = Literal["staff", "subject"]


class InterfaceCapabilities(TypedDict):
    experience: WorkspaceExperience
    role: str
    role_label: str
    allowed_views: list[str]


_ROLE_LABELS: dict[Role, str] = {
    Role.TENANT_ADMIN: "Tenant administrator",
    Role.METADATA_STEWARD: "Metadata steward",
    Role.ASSISTANCE_COORDINATOR: "Assistance coordinator",
    Role.RULE_AUTHOR: "Policy author",
    Role.RULE_APPROVER: "Release approver",
    Role.POLICY_OWNER: "Policy owner",
    Role.AUDITOR: "Auditor",
    Role.SUBJECT: "Subject",
}

# Views are deliberately granted by job responsibility, not by the fact that
# an account has authenticated with an institution's tenant domain.
_STAFF_VIEWS: dict[Role, tuple[str, ...]] = {
    Role.TENANT_ADMIN: (
        "governance",
        "institution_setup",
        "handbook_intake",
        "record_import",
        "assistance_inbox",
        "decision_review_inbox",
        "policy_review",
        "policy_ambiguities",
        "shadow_calibration",
    ),
    Role.METADATA_STEWARD: ("governance",),
    Role.ASSISTANCE_COORDINATOR: ("assistance_inbox", "decision_review_inbox"),
    Role.RULE_AUTHOR: ("handbook_intake", "record_import", "policy_ambiguities", "shadow_calibration"),
    Role.RULE_APPROVER: ("handbook_intake", "record_import", "policy_review", "policy_ambiguities", "shadow_calibration"),
    Role.POLICY_OWNER: ("policy_ambiguities", "shadow_calibration"),
    Role.AUDITOR: ("governance", "handbook_intake", "record_import", "assistance_inbox", "policy_review", "policy_ambiguities", "shadow_calibration"),
}


def get_interface_capabilities(user: UserIdentity) -> InterfaceCapabilities:
    """Return the minimum UI routing information needed by an authenticated client."""
    if user.role == Role.SUBJECT:
        return {
            "experience": "subject",
            "role": user.role.value,
            "role_label": _ROLE_LABELS[user.role],
            "allowed_views": ["policy_guides"],
        }

    return {
        "experience": "staff",
        "role": user.role.value,
        "role_label": _ROLE_LABELS[user.role],
        "allowed_views": list(_STAFF_VIEWS[user.role]),
    }
