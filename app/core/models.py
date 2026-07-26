"""
Core Domain Models for the Reasoning Engine.

This file defines the strict, decoupled Pydantic schemas that represent
the epistemological pipeline (Claims -> Facts) and the logical evaluation 
structures (ExpressionNode, RuleGraph, ReasoningGraph).
"""

from typing import List, Dict, Any, Optional, Union, Literal
from pydantic import BaseModel, Field, field_validator
import uuid
import datetime

# --- Epistemology Models ---

class Evidence(BaseModel):
    id: str = Field(default_factory=lambda: "ev_" + uuid.uuid4().hex)
    subject_id: str
    source_type: Literal["erp_system", "document_upload", "user_input"]
    storage_key: Optional[str] = None
    cryptographic_hash: str
    timestamp: str

class Claim(BaseModel):
    id: str = Field(default_factory=lambda: "cl_" + uuid.uuid4().hex)
    evidence_id: str
    target_path: str
    asserted_value: Any
    extraction_confidence: float = Field(ge=0.0, le=1.0)
    source_trust_level: float = Field(ge=0.0, le=1.0)
    status: Literal["resolved", "needs_human_review"] = "resolved"
    source_quote: Optional[str] = None
    source_locator: Optional[str] = None

class Fact(BaseModel):
    id: str = Field(default_factory=lambda: "fact_" + uuid.uuid4().hex)
    target_path: str
    resolved_value: Any
    final_confidence: float = Field(ge=0.0, le=1.0)
    status: Literal["resolved", "needs_human_review"] = "resolved"
    supporting_claims: List[str] = Field(default_factory=list)
    rejected_claims: List[str] = Field(default_factory=list)


# --- Logical Architecture Models ---

class ExpressionNode(BaseModel):
    id: str
    # Branches have an operator
    operator: Optional[Literal["AND", "OR", "NOT"]] = None
    children: Optional[List['ExpressionNode']] = None
    # Leaves have target, condition, and value
    target: Optional[str] = None
    condition: Optional[str] = None
    value: Optional[Any] = None
    
    label: str
    source_citation: Optional[str] = None

class RuleGraph(BaseModel):
    id: str = Field(default_factory=lambda: "rg_" + uuid.uuid4().hex)
    release_id: str
    root_expression: ExpressionNode
    compiled_at: str

# --- Evaluation Context ---

class EvaluationContext(BaseModel):
    tenant_id: str
    subject_id: str
    domain_id: str
    release_version: str
    # The policy selection inputs are captured with the trace so a later
    # replay proves both the rule version and why it was applicable.
    policy_as_of_date: Optional[datetime.date] = None
    policy_context: Dict[str, str] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    feature_flags: Dict[str, bool] = Field(default_factory=dict)


# --- Reasoning Engine Output Models ---

class GraphNode(BaseModel):
    id: str
    type: Literal["fact", "rule_evaluation", "conclusion"]
    label: str
    data: Dict[str, Any]
    computed_confidence: float

class GraphEdge(BaseModel):
    source_id: str
    target_id: str
    relation: str
    weight: float = 1.0

class ReasoningGraph(BaseModel):
    id: str = Field(default_factory=lambda: "trace_" + uuid.uuid4().hex)
    subject_id: str
    rule_graph_id: str
    nodes: Dict[str, GraphNode] = Field(default_factory=dict)
    edges: List[GraphEdge] = Field(default_factory=list)
    evaluation_context: Optional[EvaluationContext] = None
    # Deterministic, citation-bound prose explanation of this trace. Always
    # generated AFTER the deterministic decision exists — never influences it.
    explanation: Optional[str] = None
    
    def add_node(self, node: GraphNode):
        self.nodes[node.id] = node
        
    def add_edge(self, source_id: str, target_id: str, relation: str, weight: float = 1.0):
        self.edges.append(GraphEdge(source_id=source_id, target_id=target_id, relation=relation, weight=weight))

class EvaluationSummary(BaseModel):
    decision: Literal["ELIGIBLE", "INELIGIBLE", "NEEDS_MANUAL_REVIEW"]
    overall_confidence: float
    reasoning_graph_id: str
    release_version: str

class WorkflowRule(BaseModel):
    id: str
    trigger_condition: str
    action_type: str
    action_payload: Dict[str, Any]

class Release(BaseModel):
    id: str = Field(default_factory=lambda: "rel_" + uuid.uuid4().hex)
    domain_id: str
    version: str
    rule_graph_id: str
    digital_signature: str
    # New releases retain a complete verification bundle. Legacy releases may
    # omit these fields and remain replayable, but are not cryptographically
    # verifiable until superseded by a new signed release.
    signed_payload: Dict[str, Any] = Field(default_factory=dict)
    signed_payload_hash: Optional[str] = None
    signing_key_id: Optional[str] = None
    signing_public_key: Optional[str] = None
    effective_from: Optional[datetime.date] = None
    effective_until: Optional[datetime.date] = None
    # Domain-neutral selectors such as entry year, programme type, or region.
    # They deliberately contain policy routing inputs, never a full subject profile.
    applicability: Dict[str, List[str]] = Field(default_factory=dict)
    irp_version: str = "1.0.0"
    workflows: List[WorkflowRule] = Field(default_factory=list)

class ReplaySnapshot(BaseModel):
    timestamp: str
    evaluation_context: EvaluationContext
    compiled_rule_graph: RuleGraph
    resolved_facts: List[Fact]
    reasoning_graph: ReasoningGraph
    final_decision: str
