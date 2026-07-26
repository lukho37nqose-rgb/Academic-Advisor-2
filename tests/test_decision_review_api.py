from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import app
from app.core.models import EvaluationContext, Evidence, ReasoningGraph
from app.infrastructure.database import get_db_session
from app.infrastructure.db import Base, DBDomain, DBTenant
from app.infrastructure.repositories import (
    DecisionReviewRepository,
    EvidenceRepository,
    ReasoningRepository,
)
from app.services.auth import Role, UserIdentity, get_current_user


async def _create_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def _store_subject_trace(session_factory) -> None:
    async with session_factory() as session:
        session.add(DBTenant(id="tenant_review", name="Review Institution"))
        session.add(
            DBDomain(
                id="dom_review",
                tenant_id="tenant_review",
                name="Decision Review Domain",
                schema_definition={
                    "type": "object",
                    "access": {
                        "decision_review_enabled": True,
                        "decision_review_response_target_hours": 72,
                        "support_privacy_notice_url": "https://example.test/privacy",
                        "offline_assistance_instructions": "Call the casework office during service hours.",
                    },
                },
            )
        )
        await session.commit()

        evidence_repository = EvidenceRepository(session)
        for evidence_id in ["evidence_original", "evidence_correction"]:
            await evidence_repository.create_evidence(
                Evidence(
                    id=evidence_id,
                    subject_id="subject_1",
                    source_type="user_input",
                    storage_key=f"blob_{evidence_id}",
                    cryptographic_hash=f"hash_{evidence_id}",
                    timestamp="2026-07-25T00:00:00+00:00",
                ),
                tenant_id="tenant_review",
                domain_id="dom_review",
            )

        graph = ReasoningGraph(
            id="trace_review",
            subject_id="subject_1",
            rule_graph_id="rule_graph_review",
            evaluation_context=EvaluationContext(
                tenant_id="tenant_review",
                domain_id="dom_review",
                subject_id="subject_1",
                release_version="2026.1",
            ),
        )
        await ReasoningRepository(session).save_evaluation_artifacts(
            graph=graph,
            overall_decision="INELIGIBLE",
            overall_confidence=0.92,
            tenant_id="tenant_review",
            domain_id="dom_review",
            release_id="release_review",
            evidence_id="evidence_original",
            claims=[],
            facts=[],
        )


def _subject_identity(subject_id: str = "subject_1") -> UserIdentity:
    return UserIdentity(
        tenant_id="tenant_review",
        role=Role.SUBJECT,
        user_id=f"identity_{subject_id}",
        subject_id=subject_id,
        domain_ids=["dom_review"],
    )


def test_subject_decision_review_preserves_original_trace_and_requires_reasoned_resolution(tmp_path):
    database_path = tmp_path / "decision_review.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))
    asyncio.run(_store_subject_trace(session_factory))

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _test_db_session
    app.dependency_overrides[get_current_user] = _subject_identity
    try:
        client = TestClient(app)
        original_trace = client.get("/api/v1/reasoning/trace_review")
        submitted = client.post(
            "/api/v1/decision-reviews",
            json={
                "domain_id": "dom_review",
                "reasoning_graph_id": "trace_review",
                "category": "evidence_correction",
                "message": "The household income fact does not reflect the corrected supporting record.",
                "disputed_fact_paths": ["facts.household_income"],
                "submitted_evidence_ids": ["evidence_correction"],
            },
        )
        review_case_id = submitted.json()["id"]
        subject_list = client.get("/api/v1/decision-reviews")

        app.dependency_overrides[get_current_user] = lambda: UserIdentity(
            tenant_id="tenant_review",
            role=Role.ASSISTANCE_COORDINATOR,
            user_id="coordinator_1",
            domain_ids=["dom_review"],
        )
        staff_list = client.get("/api/v1/decision-reviews", params={"domain_id": "dom_review"})
        acknowledged = client.patch(
            f"/api/v1/admin/decision-reviews/{review_case_id}",
            json={"domain_id": "dom_review", "status": "ACKNOWLEDGED"},
        )
        under_review = client.patch(
            f"/api/v1/admin/decision-reviews/{review_case_id}",
            json={"domain_id": "dom_review", "status": "UNDER_REVIEW"},
        )
        unresolved = client.patch(
            f"/api/v1/admin/decision-reviews/{review_case_id}",
            json={"domain_id": "dom_review", "status": "RESOLVED"},
        )
        resolved = client.patch(
            f"/api/v1/admin/decision-reviews/{review_case_id}",
            json={
                "domain_id": "dom_review",
                "status": "RESOLVED",
                "resolution": "RE_EVALUATION_REQUIRED",
                "response_message": "The correction will be assessed in a new evaluation trace.",
            },
        )
        closed = client.patch(
            f"/api/v1/admin/decision-reviews/{review_case_id}",
            json={"domain_id": "dom_review", "status": "CLOSED"},
        )
        history = client.get(f"/api/v1/decision-reviews/{review_case_id}/history")

        app.dependency_overrides[get_current_user] = lambda: _subject_identity("subject_2")
        another_subject_case = client.get(f"/api/v1/decision-reviews/{review_case_id}")

        app.dependency_overrides[get_current_user] = _subject_identity
        trace_after_review = client.get("/api/v1/reasoning/trace_review")

        async def _purge_closed_case():
            async with session_factory() as session:
                return await DecisionReviewRepository(session).purge_expired_cases(
                    now=datetime.now(timezone.utc) + timedelta(days=366),
                )

        purged = asyncio.run(_purge_closed_case())
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert original_trace.status_code == 200
    assert submitted.status_code == 201
    assert submitted.json()["status"] == "SUBMITTED"
    assert submitted.json()["response_due_at"] is not None
    assert subject_list.status_code == 200
    assert subject_list.json()["items"][0]["subject_id"] == "subject_1"
    assert staff_list.status_code == 200
    assert staff_list.json()["items"][0]["id"] == review_case_id
    assert acknowledged.status_code == 200
    assert under_review.status_code == 200
    assert unresolved.status_code == 409
    assert resolved.status_code == 200
    assert resolved.json()["resolution"] == "RE_EVALUATION_REQUIRED"
    assert closed.status_code == 200
    assert closed.json()["retention_expires_at"] is not None
    assert history.status_code == 200
    assert [event["status"] for event in history.json()["items"]] == [
        "SUBMITTED",
        "ACKNOWLEDGED",
        "UNDER_REVIEW",
        "RESOLVED",
        "CLOSED",
    ]
    assert history.json()["items"][3]["response_message"] == "The correction will be assessed in a new evaluation trace."
    assert another_subject_case.status_code == 403
    assert trace_after_review.status_code == 200
    assert trace_after_review.json() == original_trace.json()
    assert purged == 1


def test_decision_review_requires_a_domain_casework_commitment(tmp_path):
    database_path = tmp_path / "decision_review_disabled.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))
    asyncio.run(_store_subject_trace(session_factory))

    async def _disable_review_casework():
        async with session_factory() as session:
            domain = await session.get(DBDomain, "dom_review")
            assert domain is not None
            schema_definition = dict(domain.schema_definition)
            access_settings = dict(schema_definition["access"])
            access_settings["decision_review_enabled"] = False
            schema_definition["access"] = access_settings
            domain.schema_definition = schema_definition
            await session.commit()

    asyncio.run(_disable_review_casework())

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _test_db_session
    app.dependency_overrides[get_current_user] = _subject_identity
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/decision-reviews",
            json={
                "domain_id": "dom_review",
                "reasoning_graph_id": "trace_review",
                "category": "missing_evidence",
                "message": "A required supporting record is missing from this evaluation.",
            },
        )
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert response.status_code == 409
    assert "not enabled" in response.json()["detail"]
