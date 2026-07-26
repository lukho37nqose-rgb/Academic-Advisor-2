from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import app
from app.core.models import Claim, EvaluationContext, Evidence, Fact, ReasoningGraph
from app.infrastructure.database import get_db_session
from app.infrastructure.db import Base, DBRelease, DBRuleGraph
from app.infrastructure.repositories import EvidenceRepository, ReasoningRepository
from app.services.auth import Role, UserIdentity, get_current_user


async def _create_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def _store_trace(session_factory) -> None:
    async with session_factory() as session:
        session.add(
            DBRelease(
                id="rel_a",
                domain_id="dom_a",
                version="1.0",
                rule_graph_id="rg_a",
                digital_signature="signature",
            )
        )
        session.add(
            DBRuleGraph(
                id="rg_a",
                release_id="rel_a",
                compiled_bytecode={"id": "root", "label": "Root", "target": "x", "condition": "==", "value": "yes"},
            )
        )
        await session.commit()

        await EvidenceRepository(session).create_evidence(
            Evidence(
                id="ev_a",
                subject_id="subject_a",
                source_type="user_input",
                storage_key="blob_a",
                cryptographic_hash="hash_a",
                timestamp="2026-07-25T00:00:00+00:00",
            ),
            tenant_id="tenant_a",
            domain_id="dom_a",
        )
        context = EvaluationContext(
            tenant_id="tenant_a",
            domain_id="dom_a",
            subject_id="subject_a",
            release_version="1.0",
        )
        graph = ReasoningGraph(
            id="trace_a",
            subject_id="subject_a",
            rule_graph_id="rg_a",
            evaluation_context=context,
        )
        winning_claim = Claim(
            id="claim_win",
            evidence_id="ev_a",
            target_path="status.active",
            asserted_value=True,
            extraction_confidence=0.95,
            source_trust_level=0.9,
            source_quote="The record is active.",
        )
        rejected_claim = Claim(
            id="claim_lost",
            evidence_id="ev_a",
            target_path="status.active",
            asserted_value=False,
            extraction_confidence=0.7,
            source_trust_level=0.5,
            source_quote="An older record says inactive.",
        )
        fact = Fact(
            id="fact_active",
            target_path="status.active",
            resolved_value=True,
            final_confidence=0.9,
            supporting_claims=[winning_claim.id],
            rejected_claims=[rejected_claim.id],
        )
        await ReasoningRepository(session).save_evaluation_artifacts(
            graph=graph,
            overall_decision="ELIGIBLE",
            overall_confidence=0.9,
            tenant_id="tenant_a",
            domain_id="dom_a",
            release_id="rel_a",
            evidence_id="ev_a",
            claims=[winning_claim, rejected_claim],
            facts=[fact],
        )


def _identity(tenant_id: str, domain_id: str) -> UserIdentity:
    return UserIdentity(
        tenant_id=tenant_id,
        role=Role.AUDITOR,
        user_id=f"auditor_{tenant_id}",
        domain_ids=[domain_id],
    )


def test_claim_and_fact_audit_records_are_persistent_and_tenant_scoped(tmp_path):
    database_path = tmp_path / "epistemic_audit.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))
    asyncio.run(_store_trace(session_factory))

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _test_db_session
    app.dependency_overrides[get_current_user] = lambda: _identity("tenant_a", "dom_a")
    try:
        client = TestClient(app)
        trace = client.get("/api/v1/reasoning/trace_a")
        claims = client.get("/api/v1/claims", params={"graph_id": "trace_a"})
        facts = client.get("/api/v1/facts", params={"graph_id": "trace_a"})

        app.dependency_overrides[get_current_user] = lambda: _identity("tenant_b", "dom_b")
        other_tenant_trace = client.get("/api/v1/reasoning/trace_a")
        other_tenant_claims = client.get("/api/v1/claims", params={"graph_id": "trace_a"})
        other_tenant_facts = client.get("/api/v1/facts", params={"graph_id": "trace_a"})
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert trace.status_code == 200
    assert trace.json()["evaluation_context"]["domain_id"] == "dom_a"

    assert claims.status_code == 200
    claim_items = claims.json()["items"]
    assert [item["id"] for item in claim_items] == ["claim_lost", "claim_win"]
    assert claim_items[1]["source_quote"] == "The record is active."

    assert facts.status_code == 200
    fact = facts.json()["items"][0]
    assert fact["supporting_claims"] == ["claim_win"]
    assert fact["rejected_claims"] == ["claim_lost"]

    assert other_tenant_trace.status_code == 404
    assert other_tenant_claims.status_code == 404
    assert other_tenant_facts.status_code == 404
