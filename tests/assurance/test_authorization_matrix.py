from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.services.auth import Role, UserIdentity, get_current_user


_EXPECTED_WORKSPACES: dict[Role, tuple[str, list[str]]] = {
    Role.TENANT_ADMIN: ("staff", ["governance", "institution_setup", "handbook_intake", "record_import", "assistance_inbox", "decision_review_inbox", "policy_review", "policy_ambiguities"]),
    Role.METADATA_STEWARD: ("staff", ["governance"]),
    Role.ASSISTANCE_COORDINATOR: ("staff", ["assistance_inbox", "decision_review_inbox"]),
    Role.RULE_AUTHOR: ("staff", ["handbook_intake", "record_import", "policy_ambiguities"]),
    Role.RULE_APPROVER: ("staff", ["handbook_intake", "record_import", "policy_review", "policy_ambiguities"]),
    Role.POLICY_OWNER: ("staff", ["policy_ambiguities"]),
    Role.AUDITOR: ("staff", ["governance", "handbook_intake", "record_import", "assistance_inbox", "policy_review", "policy_ambiguities"]),
    Role.SUBJECT: ("subject", ["policy_guides"]),
}


def _identity(role: Role) -> UserIdentity:
    return UserIdentity(
        tenant_id="tenant_assurance",
        role=role,
        user_id=f"{role.value}_1",
        subject_id="subject_1" if role == Role.SUBJECT else None,
        domain_ids=["dom_assurance"],
    )


@pytest.mark.parametrize("role,expected", _EXPECTED_WORKSPACES.items())
def test_workspace_capabilities_are_derived_from_the_full_role_matrix(
    role: Role,
    expected: tuple[str, list[str]],
) -> None:
    app.dependency_overrides[get_current_user] = lambda: _identity(role)
    try:
        response = TestClient(app).get("/api/v1/session/capabilities")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["experience"] == expected[0]
    assert response.json()["allowed_views"] == expected[1]
    assert "user_id" not in response.json()
    assert "subject_id" not in response.json()
    assert "domain_ids" not in response.json()


@pytest.mark.parametrize(
    "role",
    [
        Role.SUBJECT,
        Role.ASSISTANCE_COORDINATOR,
        Role.RULE_AUTHOR,
        Role.RULE_APPROVER,
        Role.POLICY_OWNER,
        Role.AUDITOR,
    ],
)
def test_only_metadata_roles_can_call_the_quick_edit_route(role: Role) -> None:
    app.dependency_overrides[get_current_user] = lambda: _identity(role)
    try:
        response = TestClient(app).post(
            "/api/v1/admin/quick-edit",
            json={
                "domain_id": "dom_assurance",
                "target_type": "course",
                "target_id": "ECO1010F",
                "field": "course_description",
                "new_value": "An unauthorised change.",
                "reason": "This request must be denied.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.parametrize(
    "role",
    [Role.METADATA_STEWARD, Role.RULE_AUTHOR, Role.RULE_APPROVER, Role.POLICY_OWNER],
)
def test_non_casework_staff_cannot_retrieve_a_reasoning_trace(role: Role) -> None:
    app.dependency_overrides[get_current_user] = lambda: _identity(role)
    try:
        response = TestClient(app).get("/api/v1/reasoning/trace_forbidden")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.parametrize(
    "role",
    [Role.SUBJECT, Role.ASSISTANCE_COORDINATOR, Role.RULE_AUTHOR, Role.RULE_APPROVER, Role.POLICY_OWNER],
)
def test_only_governance_roles_can_read_configured_metadata_surface(role: Role) -> None:
    app.dependency_overrides[get_current_user] = lambda: _identity(role)
    try:
        response = TestClient(app).get(
            "/api/v1/admin/permissions",
            params={"domain_id": "dom_assurance"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
