"""
Asynchronous Workflow Execution Engine.

Executes the WorkflowGraph resulting from an evaluation (e.g., updating
an external ERP system or sending an email notification). 

In an enterprise environment, this module interacts with Celery or Temporal.
Here, we expose functions designed to be executed via FastAPI's BackgroundTasks
to ensure they do not block the HTTP response cycle.
"""

import asyncio
from typing import Dict, Any, List
from app.infrastructure.telemetry import Telemetry
from app.core.models import Release, EvaluationSummary

async def execute_workflow_actions(release: Release, summary: EvaluationSummary):
    """
    Evaluates the WorkflowRules associated with a Release against the final Summary,
    and dispatches asynchronous execution for any triggered rules.
    """
    triggered_workflows = []
    
    # 1. Determine which workflows trigger
    for wf in release.workflows:
        if wf.trigger_condition == "overall == pass" and summary.decision == "ELIGIBLE":
            triggered_workflows.append(wf)
        elif wf.trigger_condition == "overall == fail" and summary.decision == "INELIGIBLE":
            triggered_workflows.append(wf)
            
    if not triggered_workflows:
        return
        
    Telemetry.log_event(
        "workflows.triggered", 
        evaluation_id=summary.reasoning_graph_id, 
        count=len(triggered_workflows)
    )
    
    # 2. Execute them concurrently without blocking
    tasks = []
    for wf in triggered_workflows:
        tasks.append(_execute_single_action(wf.id, wf.action_type, wf.action_payload, summary.reasoning_graph_id))
        
    await asyncio.gather(*tasks, return_exceptions=True)


async def _execute_single_action(workflow_id: str, action_type: str, payload: Dict[str, Any], evaluation_id: str):
    """
    The actual execution logic. Simulates network latency of talking to an ERP.
    """
    Telemetry.log_event(
        "workflow.action.started",
        workflow_id=workflow_id,
        action_type=action_type,
        evaluation_id=evaluation_id
    )
    
    try:
        # Simulate network call (e.g. POST to PeopleSoft, SendGrid)
        await asyncio.sleep(0.5) 
        
        # Here is where the actual integration logic lives:
        # if action_type == "update_student_record_system":
        #     await peoplesoft_client.update_status(payload)
        
        Telemetry.log_event(
            "workflow.action.completed",
            workflow_id=workflow_id,
            status="success"
        )
    except Exception as e:
        Telemetry.log_error(e, {"workflow_id": workflow_id, "action_type": action_type})
