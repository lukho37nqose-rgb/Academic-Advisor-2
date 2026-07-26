"""
Rule Compiler.

Responsible for taking raw JSON policy representations (drafts or human-authored rules)
and compiling them into a static `RuleGraph`. 
This is analogous to compiling source code into LLVM bytecode. It happens once per Release.
"""

import uuid
import datetime
from typing import Dict, Any, List

from .models import ExpressionNode, RuleGraph
from .operators import SUPPORTED_BRANCH_OPERATORS, SUPPORTED_LEAF_OPERATORS, UnsupportedOperatorError

def build_expression_tree(raw_node: Dict[str, Any]) -> ExpressionNode:
    """
    Recursively parses a JSON dictionary into the formal ExpressionNode model.
    Validates logical consistency (e.g., branch nodes must have children).
    """
    node_id = raw_node.get("id", "exp_" + uuid.uuid4().hex)
    label = raw_node.get("label", "Unnamed Rule")
    source_citation = raw_node.get("source_citation")
    
    # Check if it's a branch node (has operator)
    if "operator" in raw_node:
        operator = raw_node["operator"]
        if operator not in SUPPORTED_BRANCH_OPERATORS:
            raise UnsupportedOperatorError(f"Invalid branch operator '{operator}' in rule '{label}'. Supported: {SUPPORTED_BRANCH_OPERATORS}")
            
        raw_children = raw_node.get("children", [])
        if not raw_children and operator != "NOT":
             raise ValueError(f"Branch node '{label}' with operator '{operator}' must have children.")
             
        children = [build_expression_tree(child) for child in raw_children]
        
        return ExpressionNode(
            id=node_id,
            operator=operator,
            children=children,
            label=label,
            source_citation=source_citation
        )
        
    # Otherwise, it must be a leaf node
    required_leaf_keys = ["target", "condition", "value"]
    for key in required_leaf_keys:
        if key not in raw_node:
            raise ValueError(f"Leaf node '{label}' is missing required field '{key}'")

    condition = raw_node["condition"]
    if condition not in SUPPORTED_LEAF_OPERATORS:
         raise UnsupportedOperatorError(f"Invalid leaf operator '{condition}' in rule '{label}'. Supported: {SUPPORTED_LEAF_OPERATORS}")
            
    return ExpressionNode(
        id=node_id,
        target=raw_node["target"],
        condition=raw_node["condition"],
        value=raw_node["value"],
        label=label,
        source_citation=source_citation
    )

def compile_release_to_graph(release_id: str, raw_rules_payload: Dict[str, Any]) -> RuleGraph:
    """
    Takes the JSON payload authored by a Tenant Admin/Rule Author and compiles
    it into the immutable RuleGraph structure.
    
    The expected payload should have a single root node (usually an 'AND' operator)
    that encompasses all rules for that domain release.
    """
    
    if "root" not in raw_rules_payload:
        raise ValueError("Rule payload must contain a 'root' node.")
        
    root_expression = build_expression_tree(raw_rules_payload["root"])
    
    return RuleGraph(
        release_id=release_id,
        root_expression=root_expression,
        compiled_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
