from __future__ import annotations

import asyncio

from app.core.explainer import format_explanation
from app.core.models import GraphNode, ReasoningGraph


def _graph(outcome: bool | str | None, rule_status: bool | str) -> ReasoningGraph:
    nodes = {
        "rule": GraphNode(
            id="rule",
            type="rule_evaluation",
            label="Academic progress requirement",
            data={
                "passed": rule_status,
                "expected_condition": ">=",
                "citation": "Academic Progress Policy 2026, section 3.1",
            },
            computed_confidence=1.0,
        ),
    }
    if outcome is not None:
        nodes["conclusion"] = GraphNode(
            id="conclusion",
            type="conclusion",
            label="Conclusion",
            data={"overall_passed": outcome},
            computed_confidence=1.0,
        )
    return ReasoningGraph(id="trace_1", subject_id="subject_1", rule_graph_id="rule_graph_1", nodes=nodes)


def test_explanation_is_composed_from_satisfied_trace_conditions_and_citations():
    explanation = asyncio.run(format_explanation(_graph(True, True)))

    assert explanation == (
        "The published conditions evaluated in this trace are currently satisfied. "
        "Conditions evaluated: Academic progress requirement "
        "(Academic Progress Policy 2026, section 3.1)."
    )


def test_manual_review_explanation_is_explicitly_non_final():
    explanation = asyncio.run(format_explanation(_graph("NEEDS_MANUAL_REVIEW", "NEEDS_MANUAL_REVIEW")))

    assert explanation == (
        "Human consideration is required for: Academic progress requirement "
        "(Academic Progress Policy 2026, section 3.1). This is not a final "
        "institutional decision or an adverse outcome."
    )


def test_incomplete_trace_explanation_does_not_imply_an_adverse_outcome():
    explanation = asyncio.run(format_explanation(_graph(None, False)))

    assert explanation == (
        "The available trace does not contain a complete policy position. "
        "This is not a final institutional decision."
    )
