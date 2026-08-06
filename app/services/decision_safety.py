"""Product-level safeguards around a deterministic policy indication."""

from typing import Any

from app.core.models import ReasoningGraph


def requires_human_confirmation(schema_definition: dict[str, Any]) -> bool:
    """New guided domains declare their mode; legacy domains remain compatible."""
    safety = schema_definition.get("decision_safety")
    return isinstance(safety, dict) and safety.get("automation_mode") == "human_confirmation_required"


def require_human_confirmation(graph: ReasoningGraph) -> None:
    """Preserve the computed policy indication, but never present it as final."""
    conclusion = next((node for node in graph.nodes.values() if node.type == "conclusion"), None)
    if conclusion is None:
        return
    indication = conclusion.data.get("overall_passed")
    conclusion.data["policy_indication"] = indication
    conclusion.data["overall_passed"] = "NEEDS_MANUAL_REVIEW"
    conclusion.data["human_confirmation_required"] = True
