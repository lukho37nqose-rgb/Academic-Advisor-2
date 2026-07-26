import pytest
from app.core.models import ExpressionNode, Fact, ReasoningGraph, EvaluationContext
from app.core.engine import _evaluate_leaf, _evaluate_branch
from app.core.operators import SUPPORTED_LEAF_OPERATORS, SUPPORTED_BRANCH_OPERATORS, UnsupportedOperatorError
import uuid
import pydantic

def test_all_supported_leaf_operators_implemented():
    """Iterates through all supported leaf operators and ensures they don't raise an UnsupportedOperatorError."""
    
    # We provide a valid string representation of a fact for all these tests
    context = EvaluationContext(tenant_id="t1", subject_id="s1", domain_id="d1", release_version="1.0")
    
    for op in SUPPORTED_LEAF_OPERATORS:
        graph = ReasoningGraph(id=str(uuid.uuid4()), subject_id="s1", rule_graph_id="r1")
        
        # We test with string representations that can be parsed as floats if necessary
        # because the engine currently attempts float conversion for >,<,>=,<=
        node = ExpressionNode(id="n1", target="test.val", condition=op, value="10", label="Test Node")
        
        if op == "includes":
             facts = {"test.val": Fact(id="f1", target_path="test.val", resolved_value=["10", "20"], final_confidence=1.0, status="resolved")}
        else:
             facts = {"test.val": Fact(id="f1", target_path="test.val", resolved_value="15", final_confidence=1.0, status="resolved")}
        
        try:
             passed, conf = _evaluate_leaf(node, facts, graph, context)
        except UnsupportedOperatorError as e:
             pytest.fail(f"Leaf operator '{op}' is listed as supported but raised UnsupportedOperatorError: {e}")
        except Exception as e:
             # We just want to make sure it doesn't fall through to the else branch
             pass
             
def test_all_supported_branch_operators_implemented():
    """Iterates through all supported branch operators and ensures they don't raise an UnsupportedOperatorError."""
    context = EvaluationContext(tenant_id="t1", subject_id="s1", domain_id="d1", release_version="1.0")
    
    for op in SUPPORTED_BRANCH_OPERATORS:
        graph = ReasoningGraph(id=str(uuid.uuid4()), subject_id="s1", rule_graph_id="r1")
        
        child = ExpressionNode(id="child1", target="test.val", condition="==", value="10", label="Child Node")
        node = ExpressionNode(id="n1", operator=op, children=[child], label="Parent Node")
        facts = {"test.val": Fact(id="f1", target_path="test.val", resolved_value="10", final_confidence=1.0, status="resolved")}
        
        try:
             passed, conf = _evaluate_branch(node, facts, graph, context)
        except UnsupportedOperatorError as e:
             pytest.fail(f"Branch operator '{op}' is listed as supported but raised UnsupportedOperatorError: {e}")
             
def test_unsupported_leaf_operator_raises():
    context = EvaluationContext(tenant_id="t1", subject_id="s1", domain_id="d1", release_version="1.0")
    graph = ReasoningGraph(id=str(uuid.uuid4()), subject_id="s1", rule_graph_id="r1")
    node = ExpressionNode(id="n1", target="test.val", condition="MAGIC_OP", value="10", label="Test Node")
    facts = {"test.val": Fact(id="f1", target_path="test.val", resolved_value="10", final_confidence=1.0, status="resolved")}
    
    with pytest.raises(UnsupportedOperatorError):
        _evaluate_leaf(node, facts, graph, context)
        
def test_unsupported_branch_operator_raises():
    context = EvaluationContext(tenant_id="t1", subject_id="s1", domain_id="d1", release_version="1.0")
    graph = ReasoningGraph(id=str(uuid.uuid4()), subject_id="s1", rule_graph_id="r1")
    child = ExpressionNode(id="child1", target="test.val", condition="==", value="10", label="Child Node")
    
    # We bypass Pydantic's validation to inject an invalid operator for the engine test
    node = ExpressionNode.model_construct(id="n1", operator="MAGIC_BRANCH", children=[child], label="Parent Node")
    facts = {"test.val": Fact(id="f1", target_path="test.val", resolved_value="10", final_confidence=1.0, status="resolved")}
    
    with pytest.raises(UnsupportedOperatorError):
        _evaluate_branch(node, facts, graph, context)
