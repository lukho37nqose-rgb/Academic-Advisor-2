from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import app
from app.core.compiler import compile_release_to_graph
from app.core.engine import generate_reasoning_graph
from app.core.models import Claim, EvaluationContext, Fact, Release
from app.infrastructure.database import get_db_session
from app.infrastructure.db import Base, DBDomain, DBTenant
from app.infrastructure.repositories import ReasoningRepository, ReleaseRepository
from app.services.policy_source_manifest import build_policy_source_manifest


def _policy(version: str = "2026") -> dict:
    return {
        "root": {
            "id": "credits_rule",
            "label": "Completed credits meet the requirement",
            "target": "facts.completed_credits",
            "condition": ">=",
            "value": 72,
            "source_citation": f"Synthetic Faculty Handbook {version}, section 4.2",
            "policy_source": {
                "source_id": f"handbook_{version}",
                "source_version": version,
                "source_title": f"Synthetic Faculty Handbook {version}",
                "document_hash": f"sha256:{version}",
                "page_start": 104,
                "page_end": 105,
                "section": "4.2",
                "rule_identifier": "progression-credit-minimum",
                "effective_from": f"{version}-01-01",
                "display_title": f"Synthetic Faculty Handbook {version}",
                "source_anchor": f"#source-handbook-{version}-p104",
                "excerpt_reference": "Bounded source excerpt 104-105",
                "private_storage_key": "must-not-leak",
            },
        }
    }


def _context() -> EvaluationContext:
    return EvaluationContext(
        tenant_id="tenant_sources",
        subject_id="subject_1",
        domain_id="dom_sources",
        release_version="2026.1",
        source_authority="official_system",
        record_state="confirmed",
        source_system="Synthetic records",
        source_as_of=datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc),
        timestamp="2026-07-25T09:00:00+00:00",
    )


def _fact() -> Fact:
    return Fact(
        id="fact_completed_credits",
        target_path="facts.completed_credits",
        resolved_value=66,
        final_confidence=1.0,
        supporting_claims=["claim_completed_credits"],
    )


def test_policy_source_pointer_survives_compilation_and_evaluation() -> None:
    graph = compile_release_to_graph("rel_sources_2026", _policy("2026"))
    trace = generate_reasoning_graph(_context(), graph, [_fact()])
    rule_node = trace.nodes["gn_eval_credits_rule"]
    fact_node = trace.nodes["gn_fact_fact_completed_credits"]

    assert graph.root_expression.policy_source is not None
    assert graph.root_expression.policy_source.source_id == "handbook_2026"
    assert rule_node.data["citation"] == "Synthetic Faculty Handbook 2026, section 4.2"
    assert rule_node.data["policy_source"]["source_version"] == "2026"
    assert rule_node.data["policy_source"]["page_start"] == 104
    assert rule_node.data["policy_source"]["page_end"] == 105
    assert fact_node.data["source_authority"] == "official_system"
    assert "policy_source" not in fact_node.data


def test_policy_source_manifest_binds_historical_source_version() -> None:
    manifest_2026, hash_2026 = build_policy_source_manifest(_policy("2026"))
    manifest_2027, hash_2027 = build_policy_source_manifest(_policy("2027"))

    assert manifest_2026["entries"][0]["policy_source"]["source_id"] == "handbook_2026"
    assert manifest_2026["entries"][0]["policy_source"]["document_hash"] == "sha256:2026"
    assert manifest_2027["entries"][0]["policy_source"]["source_id"] == "handbook_2027"
    assert hash_2026 != hash_2027


def test_persisted_decision_keeps_original_policy_source_after_newer_policy_exists(tmp_path) -> None:
    database_path = tmp_path / "policy_source_references.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    old_rule_graph = compile_release_to_graph("rel_sources_2026", _policy("2026"))
    new_rule_graph = compile_release_to_graph("rel_sources_2027", _policy("2027"))
    old_trace = generate_reasoning_graph(_context(), old_rule_graph, [_fact()])
    claim = Claim(
        id="claim_completed_credits",
        evidence_id="evidence_credits",
        target_path="facts.completed_credits",
        asserted_value=66,
        extraction_confidence=1.0,
        source_trust_level=1.0,
        source_quote="Completed credits: 66.",
        source_locator="Synthetic transcript line 4",
    )

    async def _run() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            repository = ReasoningRepository(session)
            await repository.save_evaluation_artifacts(
                graph=old_trace,
                overall_decision="INELIGIBLE",
                overall_confidence=1.0,
                tenant_id="tenant_sources",
                domain_id="dom_sources",
                release_id="rel_sources_2026",
                evidence_id="evidence_credits",
                claims=[claim],
                facts=[_fact()],
            )
            reloaded = await repository.get_reasoning_graph(old_trace.id, tenant_id="tenant_sources")
        assert reloaded is not None
        assert reloaded.nodes["gn_eval_credits_rule"].data["policy_source"]["source_id"] == "handbook_2026"
        assert new_rule_graph.root_expression.policy_source is not None
        assert new_rule_graph.root_expression.policy_source.source_id == "handbook_2027"

    try:
        asyncio.run(_run())
    finally:
        asyncio.run(engine.dispose())


def test_public_policy_guide_exposes_safe_source_pointer_without_storage_internals(tmp_path) -> None:
    database_path = tmp_path / "public_source_pointer.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    policy = _policy("2026")
    graph = compile_release_to_graph("rel_public_sources", policy)

    async def _store() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            session.add(DBTenant(id="tenant_public_sources", name="Public Source Institution"))
            session.add(
                DBDomain(
                    id="dom_public_sources",
                    tenant_id="tenant_public_sources",
                    name="Progression",
                    schema_definition={
                        "type": "object",
                        "properties": {
                            "facts": {
                                "type": "object",
                                "properties": {
                                    "completed_credits": {"type": "number", "title": "Completed credits"},
                                },
                            },
                        },
                        "access": {"public_policy_guide": True},
                    },
                )
            )
            await session.commit()
            await ReleaseRepository(session).create_release(
                Release(
                    id="rel_public_sources",
                    domain_id="dom_public_sources",
                    version="2026.1",
                    rule_graph_id=graph.id,
                    digital_signature="signature",
                ),
                graph,
                policy["root"],
            )

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    asyncio.run(_store())
    app.dependency_overrides[get_db_session] = _test_db_session
    try:
        response = TestClient(app).get("/api/v1/public/policy-guides/dom_public_sources")
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert response.status_code == 200
    source = response.json()["policy"]["policy_source"]
    assert source == {
        "display_title": "Synthetic Faculty Handbook 2026",
        "effective_from": "2026-01-01",
        "excerpt_reference": "Bounded source excerpt 104-105",
        "page_end": 105,
        "page_start": 104,
        "rule_identifier": "progression-credit-minimum",
        "section": "4.2",
        "source_anchor": "#source-handbook-2026-p104",
        "source_id": "handbook_2026",
        "source_title": "Synthetic Faculty Handbook 2026",
        "source_version": "2026",
    }
    serialized = response.text
    assert "private_storage_key" not in serialized
    assert "must-not-leak" not in serialized
    assert "document_hash" not in serialized
