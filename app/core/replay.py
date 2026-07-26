"""Deterministic verification of a preserved institutional decision."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.core.engine import generate_reasoning_graph
from app.core.explainer import format_explanation
from app.core.models import Claim, Fact, ReasoningGraph, RuleGraph


class ReplayVerification(BaseModel):
    """A concise result which never mistakes trace retrieval for a replay."""

    status: Literal["VERIFIED", "FAILED"]
    reason: str | None = None
    decision: Literal["ELIGIBLE", "INELIGIBLE", "NEEDS_MANUAL_REVIEW"] | None = None
    overall_confidence: float | None = None


def _canonical(model: object) -> object:
    if isinstance(model, list):
        return [_canonical(item) for item in model]
    if hasattr(model, "model_dump"):
        return _canonical(model.model_dump(mode="json"))  # type: ignore[union-attr]
    if isinstance(model, dict):
        return {key: _canonical(value) for key, value in model.items()}
    return model


def _decision_from_graph(graph: ReasoningGraph) -> tuple[str, float] | None:
    conclusion = next((node for node in graph.nodes.values() if node.type == "conclusion"), None)
    if conclusion is None:
        return None
    outcome = conclusion.data.get("overall_passed")
    if outcome == "NEEDS_MANUAL_REVIEW":
        return "NEEDS_MANUAL_REVIEW", conclusion.computed_confidence
    if outcome is True:
        return "ELIGIBLE", conclusion.computed_confidence
    if outcome is False:
        return "INELIGIBLE", conclusion.computed_confidence
    return None


async def verify_replay(
    *,
    stored_graph: ReasoningGraph,
    rule_graph: RuleGraph,
    stored_claims: list[Claim],
    stored_facts: list[Fact],
    accepted_claims: list[Claim],
    accepted_facts: list[Fact],
    stored_decision: str,
    stored_confidence: float,
) -> ReplayVerification:
    """Re-run the evaluator and prove its complete stored lineage still agrees."""
    context = stored_graph.evaluation_context
    if context is None:
        return ReplayVerification(status="FAILED", reason="The stored trace lacks an evaluation context.")
    if not accepted_facts:
        return ReplayVerification(
            status="FAILED",
            reason="No accepted evidence facts remain for this preserved source version.",
        )
    if _canonical(stored_claims) != _canonical(accepted_claims):
        return ReplayVerification(
            status="FAILED",
            reason="Stored claim lineage does not match the independently accepted evidence facts.",
        )
    if _canonical(stored_facts) != _canonical(accepted_facts):
        return ReplayVerification(
            status="FAILED",
            reason="Stored resolved facts do not match the independently accepted evidence facts.",
        )

    recomputed_graph = generate_reasoning_graph(context, rule_graph, stored_facts)
    recomputed_graph.explanation = await format_explanation(recomputed_graph)

    stored_data = _canonical(stored_graph)
    recomputed_data = _canonical(recomputed_graph)
    if isinstance(stored_data, dict) and isinstance(recomputed_data, dict):
        # A trace ID identifies an execution record; it is deliberately random
        # and cannot be equal across a faithful re-evaluation.
        stored_data.pop("id", None)
        recomputed_data.pop("id", None)
    if stored_data != recomputed_data:
        return ReplayVerification(
            status="FAILED",
            reason="Re-evaluation produced a trace different from the preserved trace.",
        )

    decision = _decision_from_graph(recomputed_graph)
    if decision is None:
        return ReplayVerification(status="FAILED", reason="Re-evaluation did not produce a complete conclusion.")
    recomputed_decision, recomputed_confidence = decision
    if recomputed_decision != stored_decision or recomputed_confidence != stored_confidence:
        return ReplayVerification(
            status="FAILED",
            reason="Re-evaluation does not match the stored decision summary.",
        )
    return ReplayVerification(
        status="VERIFIED",
        decision=recomputed_decision,  # type: ignore[arg-type]
        overall_confidence=recomputed_confidence,
    )
