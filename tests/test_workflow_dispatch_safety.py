from __future__ import annotations

import asyncio

from app.core.models import EvaluationSummary, Release, WorkflowRule
from app.services.jobs import execute_workflow_actions, select_triggered_workflows


def _release() -> Release:
    return Release(
        id="release_workflow",
        domain_id="domain_workflow",
        version="1.0",
        rule_graph_id="rule_graph_workflow",
        digital_signature="synthetic",
        workflows=[
            WorkflowRule(
                id="workflow_pass",
                trigger_condition="overall == pass",
                action_type="PREPARE_NO_WRITE_EXPORT",
                action_payload={"status": "approved"},
            ),
            WorkflowRule(
                id="workflow_fail",
                trigger_condition="overall == fail",
                action_type="PREPARE_NO_WRITE_EXPORT",
                action_payload={"status": "rejected"},
            ),
        ],
    )


def test_workflow_rules_are_selected_without_external_delivery() -> None:
    summary = EvaluationSummary(
        decision="ELIGIBLE",
        overall_confidence=1.0,
        reasoning_graph_id="trace_workflow",
        release_version="1.0",
    )

    selected = select_triggered_workflows(_release(), summary)
    result = asyncio.run(execute_workflow_actions(_release(), summary))

    assert [workflow.id for workflow in selected] == ["workflow_pass"]
    assert result.triggered_workflow_ids == ("workflow_pass",)
    assert result.disposition == "DURABLE_DISPATCHER_REQUIRED"
