from __future__ import annotations

import asyncio
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import app
from app.core.compiler import compile_release_to_graph
from app.core.models import Release
from app.infrastructure.database import get_db_session
from app.infrastructure.db import Base
from app.infrastructure.repositories import ReleaseRepository
from app.services.auth import Role, UserIdentity, get_current_user


async def _create_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def test_evaluation_persists_tenant_scoped_claims_and_facts(tmp_path, monkeypatch):
    monkeypatch.setenv("REASONING_ENGINE_AI_PROVIDER", "mock")
    database_path = tmp_path / "evaluation.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))

    policy_payload = {
        "root": {
            "id": "mock_claim_rule",
            "label": "Mock extracted claim is present",
            "target": "mock.path",
            "condition": "==",
            "value": "Extracted claim from evidence.",
            "source_citation": "Reference policy section 1",
        }
    }
    rule_graph = compile_release_to_graph("rel_eval", policy_payload)

    async def _store_release() -> None:
        async with session_factory() as session:
            await ReleaseRepository(session).create_release(
                Release(
                    id="rel_eval",
                    domain_id="dom_curr_2026",
                    version="2026.1",
                    rule_graph_id=rule_graph.id,
                    digital_signature="test_signature",
                    effective_from=date(2026, 1, 1),
                    effective_until=date(2026, 12, 31),
                    applicability={"entry_year": ["2026"]},
                ),
                rule_graph,
                policy_payload["root"],
            )

    asyncio.run(_store_release())

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    def _tenant_admin() -> UserIdentity:
        return UserIdentity(
            tenant_id="tenant_demo_uni",
            role=Role.TENANT_ADMIN,
            user_id="admin_1",
            domain_ids=[],
        )

    app.dependency_overrides[get_current_user] = _tenant_admin
    app.dependency_overrides[get_db_session] = _test_db_session
    try:
        client = TestClient(app)
        ingestion = client.post(
            "/api/v1/evidence",
            json={
                "domain_id": "dom_curr_2026",
                "subject_id": "subject_1",
                "content": "Evidence used to exercise the deterministic evaluation path.",
            },
        )
        evidence_id = ingestion.json()["id"]
        missing_date = client.post(
            "/api/v1/evaluate",
            headers={"Idempotency-Key": "evaluation-missing-date-test-key"},
            json={
                "rule_graph_id": rule_graph.id,
                "evidence_id": evidence_id,
                "subject_id": "subject_1",
                "domain_id": "dom_curr_2026",
                "release_version": "2026.1",
                "applicability_context": {"entry_year": "2026"},
            },
        )
        evaluation = client.post(
            "/api/v1/evaluate",
            headers={"Idempotency-Key": "evaluation-api-test-key"},
            json={
                "rule_graph_id": rule_graph.id,
                "evidence_id": evidence_id,
                "subject_id": "subject_1",
                "domain_id": "dom_curr_2026",
                "release_version": "2026.1",
                "as_of_date": "2026-06-01",
                "applicability_context": {"entry_year": "2026"},
            },
        )
        graph_id = evaluation.json()["reasoning_graph_id"]
        claims = client.get("/api/v1/claims", params={"graph_id": graph_id})
        facts = client.get("/api/v1/facts", params={"graph_id": graph_id})
        reasoning = client.get(f"/api/v1/reasoning/{graph_id}")
        app.dependency_overrides[get_current_user] = lambda: UserIdentity(
            tenant_id="tenant_demo_uni",
            role=Role.SUBJECT,
            user_id="identity_1",
            subject_id="subject_1",
            domain_ids=["dom_curr_2026"],
        )
        cross_subject_ingestion = client.post(
            "/api/v1/evidence",
            json={
                "domain_id": "dom_curr_2026",
                "subject_id": "subject_2",
                "content": "This must never be accepted for another subject.",
            },
        )
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert ingestion.status_code == 201
    assert ingestion.json()["storage_key"].startswith("tenants/tenant_demo_uni/evidence/")
    assert missing_date.status_code == 422
    assert "as_of_date" in missing_date.json()["detail"]
    assert evaluation.status_code == 202
    assert evaluation.json()["decision"] == "ELIGIBLE"
    assert claims.status_code == 200
    assert claims.json()["items"][0]["evidence_id"] == evidence_id
    assert facts.status_code == 200
    assert facts.json()["items"][0]["supporting_claims"] == [claims.json()["items"][0]["id"]]
    assert reasoning.json()["evaluation_context"]["policy_as_of_date"] == "2026-06-01"
    assert reasoning.json()["evaluation_context"]["policy_context"] == {"entry_year": "2026"}
    assert cross_subject_ingestion.status_code == 403
