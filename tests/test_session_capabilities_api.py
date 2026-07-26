from fastapi.testclient import TestClient

from app.api import app
from app.services.auth import Role, UserIdentity, get_current_user


def _identity(role: Role) -> UserIdentity:
    return UserIdentity(
        tenant_id="tenant_demo_uni",
        role=role,
        user_id=f"{role.value}_1",
        subject_id="subject_1" if role == Role.SUBJECT else None,
        domain_ids=["dom_curr_2026"],
    )


def test_session_capabilities_expose_only_workspace_routing_information():
    app.dependency_overrides[get_current_user] = lambda: _identity(Role.RULE_AUTHOR)
    try:
        response = TestClient(app).get("/api/v1/session/capabilities")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "experience": "staff",
        "role": "rule_author",
        "role_label": "Policy author",
        "allowed_views": ["handbook_intake", "record_import", "policy_ambiguities"],
    }


def test_subject_session_has_no_staff_workspace_or_identity_values():
    app.dependency_overrides[get_current_user] = lambda: _identity(Role.SUBJECT)
    try:
        response = TestClient(app).get("/api/v1/session/capabilities")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "experience": "subject",
        "role": "subject",
        "role_label": "Subject",
        "allowed_views": ["policy_guides"],
    }


def test_policy_author_cannot_read_governance_configuration_or_reasoning_traces():
    app.dependency_overrides[get_current_user] = lambda: _identity(Role.RULE_AUTHOR)
    try:
        client = TestClient(app)
        permissions_response = client.get(
            "/api/v1/admin/permissions",
            params={"domain_id": "dom_curr_2026"},
        )
        reasoning_response = client.get("/api/v1/reasoning/trace_not_authorised")
    finally:
        app.dependency_overrides.clear()

    assert permissions_response.status_code == 403
    assert reasoning_response.status_code == 403
