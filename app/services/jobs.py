"""Fail-closed workflow dispatch planning.

The decision runtime may identify post-decision workflow rules, but it must not
pretend to call an institutional system from an in-process background task. A
production integration must use the durable outbox and a separately operated
dispatcher.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.models import EvaluationSummary, Release, WorkflowRule
from app.infrastructure.telemetry import Telemetry


@dataclass(frozen=True)
class WorkflowDispatchResult:
    """An auditable result that never represents delivery to an external system."""

    evaluation_id: str
    triggered_workflow_ids: tuple[str, ...]
    disposition: str


def select_triggered_workflows(release: Release, summary: EvaluationSummary) -> list[WorkflowRule]:
    """Deterministically select workflow rules without executing their payloads."""

    return [
        workflow
        for workflow in release.workflows
        if (
            workflow.trigger_condition == "overall == pass"
            and summary.decision == "ELIGIBLE"
        )
        or (
            workflow.trigger_condition == "overall == fail"
            and summary.decision == "INELIGIBLE"
        )
    ]


async def execute_workflow_actions(release: Release, summary: EvaluationSummary) -> WorkflowDispatchResult:
    """Record that delivery is withheld until a durable dispatcher is configured.

    This compatibility entry point remains callable, but intentionally
    does not start tasks, issue network requests, sleep, or execute payloads.
    """

    triggered = select_triggered_workflows(release, summary)
    workflow_ids = tuple(workflow.id for workflow in triggered)
    if workflow_ids:
        Telemetry.log_event(
            "workflow_dispatch_withheld",
            evaluation_id=summary.reasoning_graph_id,
            triggered_workflow_count=len(workflow_ids),
        )
        disposition = "DURABLE_DISPATCHER_REQUIRED"
    else:
        disposition = "NO_WORKFLOW_TRIGGERED"
    return WorkflowDispatchResult(
        evaluation_id=summary.reasoning_graph_id,
        triggered_workflow_ids=workflow_ids,
        disposition=disposition,
    )
