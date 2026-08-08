"""
The Reasoning Engine.

This is the core deterministic executor. It takes independently accepted Facts
and executes them against the compiled RuleGraph.
It produces the ReasoningGraph—the canonical, inspectable trace of institutional logic.
"""

from typing import Dict, Any, Tuple, Optional, List, Union
from .lineage import stable_information_reference
from .models import Fact, RuleGraph, ReasoningGraph, ExpressionNode, GraphNode, EvaluationContext
from .operators import SUPPORTED_BRANCH_OPERATORS, SUPPORTED_LEAF_OPERATORS, UnsupportedOperatorError

def _get_fact_value(facts: Dict[str, Fact], target_path: str) -> Optional[Fact]:
    """Retrieves a resolved Fact by its target path."""
    return facts.get(target_path)

def _evaluate_leaf(node: ExpressionNode, facts: Dict[str, Fact], graph: ReasoningGraph, context: EvaluationContext) -> Tuple[Union[bool, str], float]:
    """Evaluates a leaf node against the facts and adds the trace to the graph."""
    if node.condition not in SUPPORTED_LEAF_OPERATORS:
         raise UnsupportedOperatorError(f"Unsupported leaf operator encountered at runtime: {node.condition}")
         
    fact = _get_fact_value(facts, node.target or "")
    
    passed: Union[bool, str] = False
    confidence = 1.0 # Default if no fact is found
    
    # 1. Add Fact to Graph if it exists
    if fact:
        fact_node_id = f"gn_fact_{fact.id}"
        if fact_node_id not in graph.nodes:
            graph.add_node(GraphNode(
                id=fact_node_id,
                type="fact",
                label=f"Fact: {fact.target_path}",
                data={
                    "resolved_value": fact.resolved_value,
                    "source_authority": context.source_authority,
                    "record_state": context.record_state,
                    "source_system": context.source_system,
                    "source_as_of": context.source_as_of.isoformat() if context.source_as_of else None,
                    "information_id": stable_information_reference(
                        tenant_id=context.tenant_id,
                        domain_id=context.domain_id,
                        subject_id=context.subject_id,
                        fact_id=fact.id,
                    ),
                },
                computed_confidence=fact.final_confidence
            ))
        observed_value = fact.resolved_value
        confidence = fact.final_confidence
    else:
        observed_value = None
        confidence = 0.0
        
    # 2. Evaluate Logic
    if fact and fact.status == "needs_human_review":
        passed = "NEEDS_MANUAL_REVIEW"
    elif fact is None:
        # Missing institutional context is not evidence that a subject fails a
        # rule. Preserve the zero confidence, but route the position to human
        # review rather than converting an absence of data into exclusion.
        passed = "NEEDS_MANUAL_REVIEW"
    elif observed_value is not None:
        try:
            if node.condition == ">=":
                passed = float(observed_value) >= float(node.value if node.value is not None else 0)
            elif node.condition == "<=":
                passed = float(observed_value) <= float(node.value if node.value is not None else 0)
            elif node.condition == "<":
                passed = float(observed_value) < float(node.value if node.value is not None else 0)
            elif node.condition == ">":
                passed = float(observed_value) > float(node.value if node.value is not None else 0)
            elif node.condition == "==":
                passed = str(observed_value).strip().lower() == str(node.value).strip().lower()
            elif node.condition == "!=":
                passed = str(observed_value).strip().lower() != str(node.value).strip().lower()
            elif node.condition == "includes":
                if isinstance(observed_value, list):
                    passed = node.value in observed_value
                elif isinstance(observed_value, str):
                    passed = str(node.value).lower() in str(observed_value).lower()
            else:
                 raise UnsupportedOperatorError(f"Unsupported leaf operator encountered at runtime: {node.condition}")
        except (ValueError, TypeError):
            # Also catch if they bypassed the unsupported exception
            if node.condition not in SUPPORTED_LEAF_OPERATORS:
                raise UnsupportedOperatorError(f"Unsupported leaf operator encountered at runtime: {node.condition}")
            passed = False
            confidence = 0.0
    else:
        # If observed value is None and they have an invalid condition, it still raises
        if node.condition not in SUPPORTED_LEAF_OPERATORS:
             raise UnsupportedOperatorError(f"Unsupported leaf operator encountered at runtime: {node.condition}")
            
    # 3. Add Rule Evaluation to Graph
    eval_node_id = f"gn_eval_{node.id}"
    rule_data = {
        "expected_condition": node.condition,
        "expected_value": node.value,
        "passed": passed,
        "citation": node.source_citation,
        "evaluated_under_context": context.model_dump(exclude={"feature_flags"}),
    }
    if node.policy_source is not None:
        rule_data["policy_source"] = node.policy_source.model_dump(mode="json", exclude_none=True)

    graph.add_node(GraphNode(
        id=eval_node_id,
        type="rule_evaluation",
        label=node.label,
        data=rule_data,
        computed_confidence=confidence
    ))
    
    # 4. Link Fact to Rule Evaluation
    if fact:
        graph.add_edge(source_id=f"gn_fact_{fact.id}", target_id=eval_node_id, relation="evaluates_to", weight=confidence)
        
    return passed, confidence


def _evaluate_branch(node: ExpressionNode, facts: Dict[str, Fact], graph: ReasoningGraph, context: EvaluationContext) -> Tuple[Union[bool, str], float]:
    """Recursively evaluates a branch node (AND/OR)."""
    
    if node.operator not in SUPPORTED_BRANCH_OPERATORS:
        raise UnsupportedOperatorError(f"Unsupported branch operator encountered at runtime: {node.operator}")
        
    child_results = []
    child_confidences = []
    child_eval_node_ids = []
    
    if node.children:
        for child in node.children:
            passed_child, conf = _execute_node(child, facts, graph, context)
            child_results.append(passed_child)
            child_confidences.append(conf)
            child_eval_node_ids.append(f"gn_eval_{child.id}")
            
    passed: Union[bool, str] = False
    
    if node.operator == "AND":
        if any(r == "NEEDS_MANUAL_REVIEW" for r in child_results):
            passed = "NEEDS_MANUAL_REVIEW"
        else:
            passed = all(child_results)
    elif node.operator == "OR":
        if any(r == "NEEDS_MANUAL_REVIEW" for r in child_results):
            passed = "NEEDS_MANUAL_REVIEW"
        else:
            passed = any(child_results)
    elif node.operator == "NOT":
        if any(r == "NEEDS_MANUAL_REVIEW" for r in child_results):
            passed = "NEEDS_MANUAL_REVIEW"
        else:
            passed = not child_results[0] if child_results else False
    else:
        raise UnsupportedOperatorError(f"Unsupported branch operator encountered at runtime: {node.operator}")
        
    # Simplified confidence calculation for logical operators.
    if node.operator == "AND":
        confidence = min(child_confidences) if child_confidences else 1.0
    elif node.operator == "OR":
        if passed:
            passing_confs = [conf for res, conf in zip(child_results, child_confidences) if res]
            confidence = max(passing_confs) if passing_confs else 1.0
        else:
            confidence = min(child_confidences) if child_confidences else 1.0
    else:
        confidence = min(child_confidences) if child_confidences else 1.0

    eval_node_id = f"gn_eval_{node.id}"
    graph.add_node(GraphNode(
        id=eval_node_id,
        type="rule_evaluation",
        label=f"Logical {node.operator}",
        data={"passed": passed},
        computed_confidence=confidence
    ))
    
    for child_id in child_eval_node_ids:
        graph.add_edge(source_id=child_id, target_id=eval_node_id, relation="depends_on")
        
    return passed, confidence


def _execute_node(node: ExpressionNode, facts: Dict[str, Fact], graph: ReasoningGraph, context: EvaluationContext) -> Tuple[Union[bool, str], float]:
    """Router for executing a specific node in the tree."""
    if node.operator:
        return _evaluate_branch(node, facts, graph, context)
    else:
        return _evaluate_leaf(node, facts, graph, context)


def generate_reasoning_graph(context: EvaluationContext, rule_graph: RuleGraph, facts_list: List[Fact]) -> ReasoningGraph:
    """
    Takes the compiled RuleGraph and the resolved Facts, and executes them
    under the given Context to produce the dynamic ReasoningGraph.
    """
    
    graph = ReasoningGraph(
        subject_id=context.subject_id,
        rule_graph_id=rule_graph.id,
        evaluation_context=context,
    )
    
    # A target path is a deterministic input slot. Reject ambiguity rather than
    # silently allowing the final list element to overwrite an earlier fact.
    facts: Dict[str, Fact] = {}
    for fact in facts_list:
        if fact.target_path in facts:
            raise ValueError(f"Multiple facts were supplied for target path '{fact.target_path}'.")
        facts[fact.target_path] = fact
    
    # Traverse the AST
    final_passed, final_confidence = _execute_node(rule_graph.root_expression, facts, graph, context)
    
    # Add final conclusion node
    conclusion_node_id = "gn_conclusion_final"
    graph.add_node(GraphNode(
        id=conclusion_node_id,
        type="conclusion",
        label="Final Evaluation Conclusion",
        data={"overall_passed": final_passed, "context_timestamp": context.timestamp},
        computed_confidence=final_confidence
    ))
    
    root_eval_node_id = f"gn_eval_{rule_graph.root_expression.id}"
    graph.add_edge(source_id=root_eval_node_id, target_id=conclusion_node_id, relation="evaluates_to")
    
    return graph
