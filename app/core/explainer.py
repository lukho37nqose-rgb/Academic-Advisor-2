"""Deterministic, trace-bound summaries for governed subjects."""

from app.core.models import GraphNode, ReasoningGraph


def _describe_conditions(nodes: list[GraphNode]) -> str:
    descriptions: list[str] = []
    for node in nodes:
        citation = node.data.get("citation")
        if isinstance(citation, str) and citation:
            descriptions.append(f"{node.label} ({citation})")
        else:
            descriptions.append(node.label)
    return "; ".join(descriptions)


def _evaluations_with_status(graph: ReasoningGraph, status: bool | str) -> list[GraphNode]:
    return [
        node
        for node in graph.nodes.values()
        if node.type == "rule_evaluation"
        and node.data.get("passed") == status
        and node.data.get("expected_condition") is not None
    ]


async def format_explanation(graph: ReasoningGraph) -> str:
    """Return a short explanation composed only from the recorded trace."""
    conclusion = next((node for node in graph.nodes.values() if node.type == "conclusion"), None)
    outcome = conclusion.data.get("overall_passed") if conclusion else None

    if outcome == "NEEDS_MANUAL_REVIEW":
        conditions = _describe_conditions(_evaluations_with_status(graph, "NEEDS_MANUAL_REVIEW"))
        detail = f" for: {conditions}" if conditions else " under the published process"
        return (
            f"Human consideration is required{detail}. This is not a final "
            "institutional decision or an adverse outcome."
        )

    if outcome is True:
        conditions = _describe_conditions(_evaluations_with_status(graph, True))
        detail = f" Conditions evaluated: {conditions}." if conditions else ""
        return f"The published conditions evaluated in this trace are currently satisfied.{detail}"

    if outcome is False:
        conditions = _describe_conditions(_evaluations_with_status(graph, False))
        detail = f" Conditions not yet satisfied: {conditions}." if conditions else ""
        return f"One or more published conditions are not yet satisfied.{detail}"

    return (
        "The available trace does not contain a complete policy position. "
        "This is not a final institutional decision."
    )
