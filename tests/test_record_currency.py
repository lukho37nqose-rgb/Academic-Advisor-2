"""The explanation must preserve source authority separately from rule logic."""

from app.core.engine import generate_reasoning_graph
from app.core.models import EvaluationContext, ExpressionNode, Fact, RuleGraph


def test_trace_preserves_provisional_official_record_context():
    graph = generate_reasoning_graph(
        EvaluationContext(
            tenant_id="tenant_1",
            domain_id="dom_dp",
            subject_id="subject_1",
            release_version="2026.1",
            source_authority="official_system",
            record_state="provisional",
            source_system="PeopleSoft",
        ),
        RuleGraph(
            id="rule_graph_1",
            release_id="release_1",
            compiled_at="2026-07-29T00:00:00+00:00",
            root_expression=ExpressionNode(
                id="minimum_attendance",
                label="Minimum attendance",
                target="facts.attendance_met",
                condition="==",
                value=True,
            ),
        ),
        [Fact(target_path="facts.attendance_met", resolved_value=True, final_confidence=1.0)],
    )

    fact = next(node for node in graph.nodes.values() if node.type == "fact")
    assert fact.data["source_authority"] == "official_system"
    assert fact.data["record_state"] == "provisional"
    assert fact.data["source_system"] == "PeopleSoft"
