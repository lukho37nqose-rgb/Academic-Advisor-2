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
    Role.STAFF_MEMBER: "Staff member",
    Role.POLICY_EDITOR: "Policy editor",
    Role.APPROVER: "Approver",
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
        "institutional_timeline",
        "evidence_facts",
    ),
    Role.STAFF_MEMBER: (
        "governance",
        "assistance_inbox",
        "decision_review_inbox",
        "institutional_timeline",
        "evidence_facts",
    ),
    Role.POLICY_EDITOR: (
        "institution_setup",
        "handbook_intake",
        "record_import",
        "policy_ambiguities",
        "shadow_calibration",
    ),
    Role.APPROVER: (
        "handbook_intake",
        "record_import",
        "policy_review",
        "policy_ambiguities",
        "shadow_calibration",
        "institutional_timeline",
        "evidence_facts",
    ),
    Role.AUDITOR: ("governance", "handbook_intake", "record_import", "assistance_inbox", "policy_review", "policy_ambiguities", "shadow_calibration", "institutional_timeline", "evidence_facts"),
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
