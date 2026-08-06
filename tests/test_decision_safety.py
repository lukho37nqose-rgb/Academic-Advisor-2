from app.core.models import GraphNode, ReasoningGraph
from app.services.decision_safety import require_human_confirmation, requires_human_confirmation
from app.core.explainer import format_explanation


def _graph(outcome: bool) -> ReasoningGraph:
    graph = ReasoningGraph(id="synthetic_trace", subject_id="synthetic_subject", rule_graph_id="synthetic_rules")
    graph.add_node(GraphNode(id="conclusion", type="conclusion", label="Conclusion", data={"overall_passed": outcome}, computed_confidence=1.0))
    return graph


def test_human_confirmation_preserves_policy_indication_without_emitting_a_final_position() -> None:
    graph = _graph(False)

    require_human_confirmation(graph)

    conclusion = graph.nodes["conclusion"]
    assert conclusion.data["policy_indication"] is False
    assert conclusion.data["overall_passed"] == "NEEDS_MANUAL_REVIEW"
    assert "not a final" in __import__("asyncio").run(format_explanation(graph)).lower()


def test_only_explicit_new_domain_setting_requires_human_confirmation() -> None:
    assert requires_human_confirmation({"decision_safety": {"automation_mode": "human_confirmation_required"}})
    assert not requires_human_confirmation({"decision_safety": {"automation_mode": "automatic"}})
    assert not requires_human_confirmation({})
