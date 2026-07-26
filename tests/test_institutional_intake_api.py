from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import app
from app.infrastructure.database import get_db_session
from app.infrastructure.db import Base, DBDomain, DBPolicyDraft, DBTenant
from app.services.auth import Role, UserIdentity, get_current_user


async def _create_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def test_institutional_input_creates_domain_and_pending_draft_without_raw_policy_ui(tmp_path):
    database_path = tmp_path / "institutional_input.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    def _tenant_admin() -> UserIdentity:
        return UserIdentity(
            tenant_id="tenant_institution",
            role=Role.TENANT_ADMIN,
            user_id="admin_1",
        )

    app.dependency_overrides[get_current_user] = _tenant_admin
    app.dependency_overrides[get_db_session] = _test_db_session
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/institutional-inputs/domains",
            json={
                "institution_name": "Example Institution",
                "domain_name": "Research Grant Eligibility",
                "support_response_target_hours": 48,
                "decision_review_enabled": True,
                "decision_review_response_target_hours": 120,
                "support_privacy_notice_url": "https://example.test/privacy",
                "offline_assistance_instructions": "Call the Student Support desk on weekdays.",
                "facts": [
                    {"id": "requested_amount", "label": "Requested amount", "data_type": "number"},
                    {"id": "has_audit", "label": "Has recent audit", "data_type": "yes_no"},
                ],
                "rules": [
                    {
                        "id": "amount_cap",
                        "label": "Requested amount is within the funding cap",
                        "fact_id": "requested_amount",
                        "operator": "at_most",
                        "value": 50000,
                        "source_citation": "Grant Guidelines 2026, section 4.1",
                    },
                    {
                        "id": "audit_required",
                        "label": "Applicant has a recent audit",
                        "fact_id": "has_audit",
                        "operator": "equals",
                        "value": True,
                        "source_citation": "Grant Guidelines 2026, section 4.3",
                    },
                ],
            },
        )
        payload = response.json()
        pending_reviews = client.get("/api/v1/governance/drafts")
        review = client.get(f"/api/v1/governance/drafts/{payload['draft_id']}/review")

        async def _load_saved_input():
            async with session_factory() as session:
                tenant = await session.get(DBTenant, "tenant_institution")
                domain = await session.get(DBDomain, payload["domain_id"])
                draft = (await session.execute(
                    select(DBPolicyDraft).where(DBPolicyDraft.id == payload["draft_id"])
                )).scalars().one()
                return tenant, domain, draft

        tenant, domain, draft = asyncio.run(_load_saved_input())
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert response.status_code == 201
    assert payload["status"] == "PENDING_REVIEW"
    assert payload["fact_count"] == 2
    assert payload["rule_count"] == 2
    assert "policy_payload" not in payload
    assert tenant.name == "Example Institution"
    assert domain.name == "Research Grant Eligibility"
    assert domain.schema_definition["properties"]["facts"]["properties"]["requested_amount"]["type"] == "number"
    assert domain.schema_definition["access"]["support_response_target_hours"] == 48
    assert domain.schema_definition["access"]["decision_review_enabled"] is True
    assert domain.schema_definition["access"]["decision_review_response_target_hours"] == 120
    assert domain.schema_definition["access"]["offline_assistance_instructions"] == "Call the Student Support desk on weekdays."
    assert draft.status == "PENDING"
    assert draft.payload["root"]["operator"] == "AND"
    assert draft.payload["root"]["children"][0]["source_citation"] == "Grant Guidelines 2026, section 4.1"
    assert pending_reviews.status_code == 200
    assert pending_reviews.json()["items"][0]["draft_id"] == payload["draft_id"]
    assert review.status_code == 200
    assert review.json()["policy"]["kind"] == "group"
    assert review.json()["policy"]["children"][0]["fact_label"] == "Requested amount"
    assert "target" not in review.json()["policy"]["children"][0]


def test_institutional_input_rejects_operator_type_mismatch(tmp_path):
    database_path = tmp_path / "invalid_institutional_input.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_current_user] = lambda: UserIdentity(
        tenant_id="tenant_institution",
        role=Role.TENANT_ADMIN,
        user_id="admin_1",
    )
    app.dependency_overrides[get_db_session] = _test_db_session
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/institutional-inputs/domains",
            json={
                "institution_name": "Example Institution",
                "domain_name": "Invalid Policy",
                "support_privacy_notice_url": "https://example.test/privacy",
                "offline_assistance_instructions": "Call the Student Support desk on weekdays.",
                "facts": [{"id": "has_audit", "label": "Has audit", "data_type": "yes_no"}],
                "rules": [{
                    "id": "invalid_rule",
                    "label": "Audit is at least one",
                    "fact_id": "has_audit",
                    "operator": "at_least",
                    "value": 1,
                    "source_citation": "Guideline section 1",
                }],
            },
        )
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert response.status_code == 422
    assert "cannot be used" in response.json()["detail"]
