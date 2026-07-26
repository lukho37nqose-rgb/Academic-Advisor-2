from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import app
from app.core.compiler import compile_release_to_graph
from app.core.models import Release
from app.infrastructure.database import get_db_session
from app.infrastructure.db import Base, DBDomain, DBTenant
from app.infrastructure.repositories import PublicAccessRepository, ReleaseRepository
from app.services.auth import Role, UserIdentity, get_current_user


async def _create_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def test_public_policy_guide_exposes_approved_rules_and_separate_assistance(tmp_path):
    database_path = tmp_path / "public_access.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))

    payload = {
        "root": {
            "id": "income_cap",
            "label": "Income is within the support threshold",
            "target": "facts.annual_income",
            "condition": "<=",
            "value": 350000,
            "source_citation": "Support Policy 2026, section 2.1",
        }
    }
    graph = compile_release_to_graph("rel_public", payload)

    async def _store_public_domain() -> None:
        async with session_factory() as session:
            session.add(DBTenant(id="tenant_public", name="Public Institution"))
            session.add(
                DBDomain(
                    id="dom_public",
                    tenant_id="tenant_public",
                    name="Student Support Eligibility",
                    schema_definition={
                        "type": "object",
                        "properties": {
                            "facts": {
                                "type": "object",
                                "properties": {
                                    "annual_income": {"type": "number", "title": "Annual household income"},
                                },
                            },
                        },
                        "access": {
                            "public_policy_guide": True,
                            "assistance_requests_enabled": True,
                            "support_response_target_hours": 48,
                            "support_privacy_notice_url": "https://example.test/privacy",
                            "offline_assistance_instructions": "Call the Student Support desk on weekdays.",
                        },
                    },
                )
            )
            await session.commit()
            await ReleaseRepository(session).create_release(
                Release(
                    id="rel_public",
                    domain_id="dom_public",
                    version="2026.1",
                    rule_graph_id=graph.id,
                    digital_signature="signature",
                ),
                graph,
                payload["root"],
            )

    asyncio.run(_store_public_domain())

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _test_db_session
    try:
        client = TestClient(app)
        listing = client.get("/api/v1/public/policy-guides")
        guide = client.get("/api/v1/public/policy-guides/dom_public")
        support = client.post(
            "/api/v1/public/policy-guides/dom_public/support",
            json={
                "category": "unique_circumstance",
                "contact_details": "person@example.test",
                "message": "My circumstances are not represented by the published conditions.",
            },
        )

        app.dependency_overrides[get_current_user] = lambda: UserIdentity(
            tenant_id="tenant_public",
            role=Role.ASSISTANCE_COORDINATOR,
            user_id="coordinator_1",
            domain_ids=["dom_public"],
        )
        domains = client.get("/api/v1/admin/domains")
        requests = client.get("/api/v1/admin/support-requests", params={"domain_id": "dom_public"})
        request_id = requests.json()["items"][0]["id"]
        status_update = client.patch(
            f"/api/v1/admin/support-requests/{request_id}",
            json={"domain_id": "dom_public", "status": "IN_PROGRESS"},
        )
        closed = client.patch(
            f"/api/v1/admin/support-requests/{request_id}",
            json={"domain_id": "dom_public", "status": "CLOSED"},
        )
        history = client.get(
            f"/api/v1/admin/support-requests/{request_id}/history",
            params={"domain_id": "dom_public"},
        )
        async def _purge_expired_requests():
            async with session_factory() as session:
                return await PublicAccessRepository(session).purge_expired_support_requests(
                    now=datetime.now(timezone.utc) + timedelta(days=91),
                )

        purged = asyncio.run(_purge_expired_requests())
        app.dependency_overrides[get_current_user] = lambda: UserIdentity(
            tenant_id="tenant_public",
            role=Role.AUDITOR,
            user_id="auditor_1",
            domain_ids=["dom_public"],
        )
        auditor_update = client.patch(
            f"/api/v1/admin/support-requests/{request_id}",
            json={"domain_id": "dom_public", "status": "CLOSED"},
        )
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert listing.status_code == 200
    assert listing.json()["items"] == [{
        "domain_id": "dom_public",
        "domain_name": "Student Support Eligibility",
        "version": "2026.1",
    }]
    assert guide.status_code == 200
    rule = guide.json()["policy"]
    assert rule["fact_label"] == "Annual household income"
    assert rule["citation"] == "Support Policy 2026, section 2.1"
    assert "target" not in rule
    assert support.status_code == 202
    assert domains.status_code == 200
    assert domains.json()["items"] == [{"domain_id": "dom_public", "domain_name": "Student Support Eligibility"}]
    assert requests.status_code == 200
    assert requests.json()["items"][0]["category"] == "unique_circumstance"
    assert requests.json()["items"][0]["status"] == "OPEN"
    assert requests.json()["items"][0]["response_due_at"] is not None
    assert status_update.status_code == 200
    assert status_update.json()["status"] == "IN_PROGRESS"
    assert closed.status_code == 200
    assert closed.json()["retention_expires_at"] is not None
    assert history.status_code == 200
    assert [event["status"] for event in history.json()["items"]] == ["OPEN", "IN_PROGRESS", "CLOSED"]
    assert history.json()["items"][1]["actor_id"] == "coordinator_1"
    assert purged == 1
    assert auditor_update.status_code == 403


def test_public_support_is_rate_limited_before_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLIC_SUPPORT_RATE_LIMIT_MAX", "1")
    monkeypatch.setenv("PUBLIC_SUPPORT_RATE_LIMIT_WINDOW_SECONDS", "60")
    database_path = tmp_path / "public_access_rate_limit.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _test_db_session
    payload = {
        "category": "other",
        "message": "I need help with this institutional process.",
    }

    try:
        with TestClient(app) as client:
            first = client.post("/api/v1/public/policy-guides/dom_rate_limit_unique/support", json=payload)
            second = client.post("/api/v1/public/policy-guides/dom_rate_limit_unique/support", json=payload)
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert first.status_code == 404
    assert second.status_code == 429
    assert second.headers["Retry-After"]
