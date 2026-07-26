from __future__ import annotations

import asyncio

from app.core.engine import generate_reasoning_graph
from app.core.explainer import format_explanation
from app.core.models import Claim, EvaluationContext, ExpressionNode, Fact, RuleGraph
from app.core.replay import verify_replay


def _verified_fixture():
    context = EvaluationContext(
        tenant_id="tenant_replay",
        subject_id="subject_replay",
        domain_id="domain_replay",
        release_version="2026.1",
        timestamp="2026-07-26T12:00:00+00:00",
    )
    rule_graph = RuleGraph(
        id="rule_graph_replay",
        release_id="release_replay",
        compiled_at="2026-07-26T11:00:00+00:00",
        root_expression=ExpressionNode(
            id="minimum_credits",
            label="Completed credits meet the minimum",
            target="facts.completed_credits",
            condition=">=",
            value=120,
            source_citation="Academic rule 4.1",
        ),
    )
    claim = Claim(
        id="claim_accepted_fact",
        evidence_id="evidence_replay",
        target_path="facts.completed_credits",
        asserted_value=132,
        extraction_confidence=1.0,
        source_trust_level=1.0,
        source_quote="Completed credits: 132.",
        source_locator="Transcript line 8",
    )
    fact = Fact(
        id="fact_accepted_fact",
        target_path="facts.completed_credits",
        resolved_value=132,
        final_confidence=1.0,
        supporting_claims=[claim.id],
    )
    graph = generate_reasoning_graph(context, rule_graph, [fact])
    graph.explanation = asyncio.run(format_explanation(graph))
    return rule_graph, claim, fact, graph


def test_replay_verifier_recomputes_and_rejects_changed_fact_lineage():
    rule_graph, claim, accepted_fact, graph = _verified_fixture()

    verified = asyncio.run(
        verify_replay(
            stored_graph=graph,
            rule_graph=rule_graph,
            stored_claims=[claim],
            stored_facts=[accepted_fact],
            accepted_claims=[claim],
            accepted_facts=[accepted_fact],
            stored_decision="ELIGIBLE",
            stored_confidence=1.0,
        )
    )
    changed_fact = accepted_fact.model_copy(update={"resolved_value": 12})
    rejected = asyncio.run(
        verify_replay(
            stored_graph=graph,
            rule_graph=rule_graph,
            stored_claims=[claim],
            stored_facts=[changed_fact],
            accepted_claims=[claim],
            accepted_facts=[accepted_fact],
            stored_decision="ELIGIBLE",
            stored_confidence=1.0,
        )
    )

    assert verified.status == "VERIFIED"
    assert rejected.status == "FAILED"
    assert rejected.reason == "Stored resolved facts do not match the independently accepted evidence facts."
