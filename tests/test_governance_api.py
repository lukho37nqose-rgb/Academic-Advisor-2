from __future__ import annotations

import asyncio
from datetime import date

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import app
from app.core.compiler import compile_release_to_graph
from app.core.models import Release
from app.infrastructure.db import Base, DBPolicyDraft
from app.infrastructure.database import get_db_session
from app.infrastructure.repositories import (
    PolicyAmbiguityConflictError,
    PolicyAmbiguityRepository,
    DraftRepository,
    ReleaseApplicabilityConflictError,
    ReleaseRepository,
    ReleaseVersionConflictError,
)
from app.services.auth import Role, UserIdentity, get_current_user


async def _unused_db_session():
    yield object()


def _policy_editor() -> UserIdentity:
    return UserIdentity(
        tenant_id="tenant_demo_uni",
        role=Role.POLICY_EDITOR,
        user_id="author_1",
        domain_ids=["dom_curr_2026"],
    )


def _staff_member() -> UserIdentity:
    return UserIdentity(
        tenant_id="tenant_demo_uni",
        role=Role.STAFF_MEMBER,
        user_id="steward_1",
        domain_ids=["dom_curr_2026"],
    )


def _approver() -> UserIdentity:
    return UserIdentity(
        tenant_id="tenant_demo_uni",
        role=Role.APPROVER,
        user_id="approver_1",
        domain_ids=["dom_curr_2026"],
    )


async def _create_schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def test_draft_policy_rejects_uncompilable_payload_before_persistence():
    app.dependency_overrides[get_current_user] = _policy_editor
    app.dependency_overrides[get_db_session] = _unused_db_session
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/governance/drafts",
            json={
                "domain_id": "dom_curr_2026",
                "policy_name": "Bad draft",
                "payload": {
                    "root": {
                        "label": "Bad root",
                        "operator": "XOR",
                        "children": [],
                    }
                },
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "Draft failed compilation" in response.json()["detail"]


def test_quick_edit_applies_metadata_overlay_and_audit_log(tmp_path):
    db_path = tmp_path / "governance.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_current_user] = _staff_member
    app.dependency_overrides[get_db_session] = _test_db_session
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/quick-edit",
            json={
                "domain_id": "dom_curr_2026",
                "target_type": "course",
                "target_id": "ECO1010F",
                "field": "course_description",
                "old_value": "Introductory economics.",
                "new_value": "Introductory microeconomics and macroeconomics.",
                "reason": "Aligned display text with handbook page 14.",
                "source_reference": "2026 handbook p.14",
            },
        )
        audit_response = client.get(
            "/api/v1/admin/quick-edits",
            params={"domain_id": "dom_curr_2026", "target_id": "ECO1010F"},
        )
        overlay_response = client.get(
            "/api/v1/admin/metadata-overrides",
            params={"domain_id": "dom_curr_2026", "target_id": "ECO1010F"},
        )
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "applied"
    assert body["field"] == "course_description"
    assert body["applied_by"] == "steward_1"
    assert body["field_policy"]["risk"] == "low"

    assert audit_response.status_code == 200
    audit_items = audit_response.json()["items"]
    assert len(audit_items) == 1
    assert audit_items[0]["new_value"] == "Introductory microeconomics and macroeconomics."

    assert overlay_response.status_code == 200
    overlay_items = overlay_response.json()["items"]
    assert len(overlay_items) == 1
    assert overlay_items[0]["current_value"] == "Introductory microeconomics and macroeconomics."


def test_quick_edit_rejects_rule_bearing_fields():
    app.dependency_overrides[get_current_user] = _staff_member
    app.dependency_overrides[get_db_session] = _unused_db_session
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/quick-edit",
            json={
                "domain_id": "dom_curr_2026",
                "target_type": "course",
                "target_id": "ECO1010F",
                "field": "prerequisite",
                "new_value": "MAT1013F",
                "reason": "This belongs in structured review.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "not configured as a low-risk metadata quick edit" in response.text


def test_quick_edit_rejects_unknown_metadata_target():
    app.dependency_overrides[get_current_user] = _staff_member
    app.dependency_overrides[get_db_session] = _unused_db_session
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/quick-edit",
            json={
                "domain_id": "dom_curr_2026",
                "target_type": "course",
                "target_id": "NOT_A_COURSE",
                "field": "course_description",
                "new_value": "This target is not in the approved catalogue.",
                "reason": "Validate catalogue-bound metadata edits.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert "approved metadata catalogue" in response.json()["detail"]


def test_permission_matrix_exposes_role_boundaries():
    app.dependency_overrides[get_current_user] = _staff_member
    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/admin/permissions",
            params={"domain_id": "dom_curr_2026"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["current_role"] == "staff_member"
    course_policy = next(
        target for target in body["metadata_quick_edits"] if target["target_type"] == "course"
    )
    assert "course_description" in [field["name"] for field in course_policy["fields"]]
    steward_row = next(row for row in body["matrix"] if row["role"] == "staff_member")
    assert steward_row["can_author_structured_drafts"] is False
    assert steward_row["can_approve_releases"] is False


def test_edge_governance_policy_is_domain_specific():
    def _grant_steward() -> UserIdentity:
        return UserIdentity(
            tenant_id="tenant_demo_foundation",
            role=Role.STAFF_MEMBER,
            user_id="grant_steward_1",
            domain_ids=["dom_grant_2024"],
        )

    app.dependency_overrides[get_current_user] = _grant_steward
    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/admin/permissions",
            params={"domain_id": "dom_grant_2024"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    target = response.json()["metadata_quick_edits"][0]
    assert target["target_type"] == "programme"
    assert "display_name" in [field["name"] for field in target["fields"]]
    assert "course_description" not in [field["name"] for field in target["fields"]]


def test_release_versions_are_unique_with_a_database_backstop(tmp_path):
    database_path = tmp_path / "release_versions.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))

    payload = {
        "root": {
            "id": "rule_root",
            "label": "Active status",
            "target": "status.active",
            "condition": "==",
            "value": True,
        }
    }

    async def _create_duplicate_version() -> None:
        async with session_factory() as session:
            repository = ReleaseRepository(session)
            first_graph = compile_release_to_graph("rel_one", payload)
            await repository.create_release(
                Release(
                    id="rel_one",
                    domain_id="dom_curr_2026",
                    version="2026.1",
                    rule_graph_id=first_graph.id,
                    digital_signature="signature_one",
                ),
                first_graph,
                payload["root"],
            )

            second_graph = compile_release_to_graph("rel_two", payload)
            with pytest.raises(ReleaseVersionConflictError):
                await repository.create_release(
                    Release(
                        id="rel_two",
                        domain_id="dom_curr_2026",
                        version="2026.1",
                        rule_graph_id=second_graph.id,
                        digital_signature="signature_two",
                    ),
                    second_graph,
                    payload["root"],
                )

    try:
        asyncio.run(_create_duplicate_version())
    finally:
        asyncio.run(engine.dispose())


def test_publish_persists_release_approval_metadata(tmp_path):
    database_path = tmp_path / "release_approval.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))

    payload = {
        "root": {
            "id": "rule_root",
            "label": "Active status",
            "target": "status.active",
            "condition": "==",
            "value": True,
        }
    }

    async def _publish_release() -> None:
        async with session_factory() as session:
            draft_repo = DraftRepository(session)
            release_repo = ReleaseRepository(session)
            await draft_repo.create_draft(
                draft_id="draft_publish_1",
                tenant_id="tenant_demo_uni",
                domain_id="dom_curr_2026",
                policy_name="Approval trail draft",
                author_id="author_1",
                payload=payload,
            )
            rule_graph = compile_release_to_graph("rel_publish_1", payload)
            await release_repo.create_release(
                Release(
                    id="rel_publish_1",
                    domain_id="dom_curr_2026",
                    version="2026.3",
                    rule_graph_id=rule_graph.id,
                    digital_signature="signature_publish_1",
                ),
                rule_graph,
                payload["root"],
                draft_id="draft_publish_1",
                approved_by="approver_1",
            )

            draft_row = await session.get(DBPolicyDraft, "draft_publish_1")
            assert draft_row is not None
            assert draft_row.status == "RELEASED"
            assert draft_row.approved_by == "approver_1"
            assert draft_row.approved_at is not None
            assert draft_row.released_as_release_id == "rel_publish_1"

    try:
        asyncio.run(_publish_release())
    finally:
        asyncio.run(engine.dispose())


def test_policy_ambiguities_require_a_different_authorised_resolver(tmp_path):
    database_path = tmp_path / "policy_ambiguities.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))

    async def _exercise_register() -> None:
        async with session_factory() as session:
            repository = PolicyAmbiguityRepository(session)
            created = await repository.create(
                ambiguity_id="amb_one",
                tenant_id="tenant_demo_uni",
                domain_id="dom_curr_2026",
                source_citation="Handbook section 4.2",
                question="Does this transition rule apply to a returning subject?",
                interpretation_options=["Apply it", "Do not apply it"],
                affected_target_paths=["facts.entry_year"],
                created_by="author_1",
            )
            assert created["status"] == "OPEN"
            assert await repository.has_open_ambiguities(
                tenant_id="tenant_demo_uni", domain_id="dom_curr_2026", affected_target_paths={"facts.entry_year"}
            )
            assert not await repository.has_open_ambiguities(
                tenant_id="tenant_demo_uni", domain_id="dom_curr_2026", affected_target_paths={"facts.completed_credits"}
            )

            with pytest.raises(PolicyAmbiguityConflictError, match="Separation of duties"):
                await repository.resolve(
                    ambiguity_id="amb_one",
                    tenant_id="tenant_demo_uni",
                    domain_id="dom_curr_2026",
                    resolution="Apply the transition rule.",
                    source_reference="Senate resolution 2026/14",
                    actor_id="author_1",
                )

            resolved = await repository.resolve(
                ambiguity_id="amb_one",
                tenant_id="tenant_demo_uni",
                domain_id="dom_curr_2026",
                resolution="Apply the transition rule to all returning subjects.",
                source_reference="Senate resolution 2026/14",
                actor_id="approver_1",
            )
            assert resolved is not None
            assert resolved["status"] == "RESOLVED"
            assert not await repository.has_open_ambiguities(
                tenant_id="tenant_demo_uni", domain_id="dom_curr_2026", affected_target_paths={"facts.entry_year"}
            )

    try:
        asyncio.run(_exercise_register())
    finally:
        asyncio.run(engine.dispose())


def test_policy_ambiguity_api_uses_role_and_domain_scoped_workflow(tmp_path):
    database_path = tmp_path / "policy_ambiguity_api.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_current_user] = _policy_editor
    app.dependency_overrides[get_db_session] = _test_db_session
    try:
        client = TestClient(app)
        created = client.post(
            "/api/v1/governance/policy-ambiguities",
            json={
                "domain_id": "dom_curr_2026",
                "source_citation": "Handbook section 4.2",
                "question": "Does this transition rule apply to a returning subject?",
                "interpretation_options": ["Apply it", "Do not apply it"],
            },
        )
        ambiguity_id = created.json()["ambiguity_id"]
        listed = client.get(
            "/api/v1/governance/policy-ambiguities",
            params={"domain_id": "dom_curr_2026", "status": "OPEN"},
        )
        app.dependency_overrides[get_current_user] = _approver
        resolved = client.patch(
            f"/api/v1/governance/policy-ambiguities/{ambiguity_id}/resolve",
            json={
                "domain_id": "dom_curr_2026",
                "resolution": "Apply the transition rule to returning subjects.",
                "source_reference": "Senate resolution 2026/14",
            },
        )
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert created.status_code == 201
    assert listed.status_code == 200
    assert listed.json()["items"][0]["status"] == "OPEN"
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "RESOLVED"


def test_release_applicability_periods_cannot_overlap_for_the_same_context(tmp_path):
    database_path = tmp_path / "release_applicability.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))
    payload = {
        "root": {
            "id": "rule_root",
            "label": "Active status",
            "target": "status.active",
            "condition": "==",
            "value": True,
        }
    }

    async def _create_scheduled_releases() -> None:
        async with session_factory() as session:
            repository = ReleaseRepository(session)
            first_graph = compile_release_to_graph("rel_cohort_2026", payload)
            await repository.create_release(
                Release(
                    id="rel_cohort_2026",
                    domain_id="dom_curr_2026",
                    version="2026.1",
                    rule_graph_id=first_graph.id,
                    digital_signature="signature_one",
                    effective_from=date(2026, 1, 1),
                    applicability={"entry_year": ["2026"]},
                ),
                first_graph,
                payload["root"],
            )

            distinct_graph = compile_release_to_graph("rel_cohort_2027", payload)
            await repository.create_release(
                Release(
                    id="rel_cohort_2027",
                    domain_id="dom_curr_2026",
                    version="2026.2",
                    rule_graph_id=distinct_graph.id,
                    digital_signature="signature_two",
                    effective_from=date(2026, 1, 1),
                    applicability={"entry_year": ["2027"]},
                ),
                distinct_graph,
                payload["root"],
            )

            overlapping_graph = compile_release_to_graph("rel_cohort_2026_overlap", payload)
            with pytest.raises(ReleaseApplicabilityConflictError, match="overlap"):
                await repository.create_release(
                    Release(
                        id="rel_cohort_2026_overlap",
                        domain_id="dom_curr_2026",
                        version="2026.3",
                        rule_graph_id=overlapping_graph.id,
                        digital_signature="signature_three",
                        effective_from=date(2026, 6, 1),
                        applicability={"entry_year": ["2026"]},
                    ),
                    overlapping_graph,
                    payload["root"],
                )

    try:
        asyncio.run(_create_scheduled_releases())
    finally:
        asyncio.run(engine.dispose())
