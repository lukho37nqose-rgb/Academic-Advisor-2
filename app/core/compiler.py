"""
Rule Compiler.

Responsible for taking raw JSON policy representations (drafts or human-authored rules)
and compiling them into a static `RuleGraph`. 
This is analogous to compiling source code into LLVM bytecode. It happens once per Release.
"""

import hashlib
import datetime
from typing import Dict, Any, Set

from .models import ExpressionNode, PolicySourceReference, RuleGraph
from .operators import SUPPORTED_BRANCH_OPERATORS, SUPPORTED_LEAF_OPERATORS, UnsupportedOperatorError

def _stable_node_id(node_path: tuple[int, ...]) -> str:
    path_text = "root" if not node_path else "root:" + ":".join(str(index) for index in node_path)
    digest = hashlib.sha256(path_text.encode("utf-8")).hexdigest()[:16]
    return f"exp_{digest}"


def build_expression_tree(
    raw_node: Dict[str, Any],
    *,
    seen_node_ids: Set[str] | None = None,
    node_path: tuple[int, ...] = (),
) -> ExpressionNode:
    """
    Recursively parses a JSON dictionary into the formal ExpressionNode model.
    Validates logical consistency (e.g., branch nodes must have children).
    """
    node_id = raw_node.get("id") or _stable_node_id(node_path)
    seen_node_ids = seen_node_ids if seen_node_ids is not None else set()
    if node_id in seen_node_ids:
        raise ValueError(f"Rule node id '{node_id}' is duplicated; rule node ids must be unique.")
    seen_node_ids.add(node_id)
    label = raw_node.get("label", "Unnamed Rule")
    source_citation = raw_node.get("source_citation")
    raw_policy_source = raw_node.get("policy_source") or raw_node.get("policy_source_reference")
    policy_source = (
        PolicySourceReference.model_validate(raw_policy_source)
        if isinstance(raw_policy_source, dict)
        else None
    )
    
    # Check if it's a branch node (has operator)
    if "operator" in raw_node:
        operator = raw_node["operator"]
        if operator not in SUPPORTED_BRANCH_OPERATORS:
            raise UnsupportedOperatorError(f"Invalid branch operator '{operator}' in rule '{label}'. Supported: {SUPPORTED_BRANCH_OPERATORS}")
            
        raw_children = raw_node.get("children", [])
        if not raw_children:
             raise ValueError(f"Branch node '{label}' with operator '{operator}' must have children.")
        if operator == "NOT" and len(raw_children) != 1:
             raise ValueError(f"Branch node '{label}' with operator 'NOT' must have exactly one child.")
             
        children = [
            build_expression_tree(child, seen_node_ids=seen_node_ids, node_path=node_path + (index,))
            for index, child in enumerate(raw_children)
        ]
        
        return ExpressionNode(
            id=node_id,
            operator=operator,
            children=children,
            label=label,
            source_citation=source_citation,
            policy_source=policy_source,
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
        source_citation=source_citation,
        policy_source=policy_source,
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
