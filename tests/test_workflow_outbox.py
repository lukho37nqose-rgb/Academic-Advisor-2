"""Workflow intents are signed release content and remain held after evaluation."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.models import (
    Claim,
    EvaluationContext,
    Fact,
    GraphNode,
    ReasoningGraph,
    Release,
    WorkflowRule,
)
from app.infrastructure.db import Base, DBWorkflowOutbox
from app.infrastructure.repositories import ReasoningRepository


@pytest.mark.asyncio
async def test_triggered_workflow_is_written_as_held_outbox_record(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'workflow.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    context = EvaluationContext(
        tenant_id="tenant_a", subject_id="subject_a", domain_id="domain_a", release_version="2026.1"
    )
    graph = ReasoningGraph(subject_id="subject_a", rule_graph_id="graph_a", evaluation_context=context)
    graph.add_node(GraphNode(
        id="gn_conclusion_final", type="conclusion", label="Conclusion",
        data={"overall_passed": True}, computed_confidence=1.0,
    ))
    release = Release(
        id="release_a", domain_id="domain_a", version="2026.1", rule_graph_id="graph_a",
        digital_signature="test", workflows=[WorkflowRule(
            id="staff_follow_up", trigger_condition="overall == pass",
            action_type="CREATE_INTERNAL_TASK", action_payload={"queue": "admissions"},
        )],
    )
    claim = Claim(evidence_id="evidence_a", target_path="facts.ready", asserted_value=True,
                  extraction_confidence=1, source_trust_level=1)
    fact = Fact(target_path="facts.ready", resolved_value=True, final_confidence=1, supporting_claims=[claim.id])

    async with session_factory() as session:
        await ReasoningRepository(session).save_evaluation_artifacts(
            graph=graph, overall_decision="ELIGIBLE", overall_confidence=1,
            tenant_id="tenant_a", domain_id="domain_a", release_id="release_a", evidence_id="evidence_a",
            claims=[claim], facts=[fact], release=release,
        )
        outbox = (await session.execute(select(DBWorkflowOutbox))).scalars().all()

    assert len(outbox) == 1
    assert outbox[0].status == "HELD"
    assert outbox[0].action_payload == {"queue": "admissions"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_non_triggered_workflow_creates_no_outbox_record(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'workflow_none.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    context = EvaluationContext(tenant_id="tenant_a", subject_id="subject_a", domain_id="domain_a", release_version="2026.1")
    graph = ReasoningGraph(subject_id="subject_a", rule_graph_id="graph_a", evaluation_context=context)
    release = Release(id="release_a", domain_id="domain_a", version="2026.1", rule_graph_id="graph_a", digital_signature="test", workflows=[WorkflowRule(id="only_failures", trigger_condition="overall == fail", action_type="CREATE_INTERNAL_TASK", action_payload={})])
    async with session_factory() as session:
        await ReasoningRepository(session).save_evaluation_artifacts(
            graph=graph, overall_decision="ELIGIBLE", overall_confidence=1,
            tenant_id="tenant_a", domain_id="domain_a", release_id="release_a", evidence_id="evidence_a",
            claims=[], facts=[], release=release,
        )
        outbox = (await session.execute(select(DBWorkflowOutbox))).scalars().all()
    assert outbox == []
    await engine.dispose()
