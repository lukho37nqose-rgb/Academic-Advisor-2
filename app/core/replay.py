"""
The Replay Engine.

The killer enterprise feature for appeals and auditing.
Reconstructs the exact state of an evaluation at a specific point in time,
tying together the ReasoningGraph, RuleGraph, Facts, and Evidence.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel
from .models import ReasoningGraph, RuleGraph
from ..infrastructure.repositories import ReasoningRepository, ReleaseRepository

class ReplaySnapshot(BaseModel):
    """A complete, self-contained snapshot of an evaluation for audit purposes."""
    reasoning_graph: ReasoningGraph
    rule_graph: RuleGraph
    # In a full implementation, this would also include the Evidence and Claims 
    # fetched from the DB using the IDs referenced in the graph nodes.


async def reconstruct_evaluation(
    graph_id: str,
    tenant_id: str,
    reasoning_repo: ReasoningRepository,
    release_repo: ReleaseRepository,
) -> Optional[ReplaySnapshot]:
    """
    Fetches the dynamic trace and the static policy bytecode used to generate it.
    This guarantees that even if a policy changed yesterday, an appeal today
    can view exactly what happened under the old policy.
    """
    
    # 1. Fetch the execution trace
    reasoning_graph = await reasoning_repo.get_reasoning_graph(graph_id, tenant_id=tenant_id)
    if not reasoning_graph:
        return None
        
    # 2. Fetch the exact policy version used
    rule_graph = await release_repo.get_compiled_rule_graph(reasoning_graph.rule_graph_id)
    if not rule_graph:
        raise ValueError(f"CRITICAL AUDIT FAILURE: RuleGraph {reasoning_graph.rule_graph_id} referenced by ReasoningGraph {graph_id} is missing from the database.")
        
    # 3. Compile the Replay Artifact
    return ReplaySnapshot(
        reasoning_graph=reasoning_graph,
        rule_graph=rule_graph
    )
