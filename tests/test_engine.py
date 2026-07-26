"""
Tests for the deterministic Reasoning Engine.
Ensures logic gates (AND, OR, NOT, values) resolve correctly against facts.
"""

import pytest
from typing import Dict
from app.core.models import Fact, EvaluationContext, RuleGraph
from app.core.engine import generate_reasoning_graph
from app.core.compiler import compile_release_to_graph
from app.sdk.policy import DomainBuilder, Rule

@pytest.fixture
def base_context() -> EvaluationContext:
    return EvaluationContext(
        tenant_id="test_tenant",
        subject_id="test_subject",
        domain_id="test_domain",
        release_version="1.0"
    )

def test_engine_evaluates_simple_passing_rule(base_context: EvaluationContext):
    builder = DomainBuilder("Test Domain").require(Rule("target.value").gte(10))
    rule_graph = compile_release_to_graph("rel_1", builder.compile())
    
    facts = [Fact(target_path="target.value", resolved_value=15, final_confidence=1.0)]
    
    reasoning_graph = generate_reasoning_graph(base_context, rule_graph, facts)
    
    conclusion = next(n for n in reasoning_graph.nodes.values() if n.type == "conclusion")
    assert conclusion.data["overall_passed"] is True
    assert conclusion.computed_confidence == 1.0


def test_engine_evaluates_failing_logical_and(base_context: EvaluationContext):
    builder = DomainBuilder("Test Domain")
    builder.require(Rule("a").eq(1))
    builder.require(Rule("b").eq(2))
    rule_graph = compile_release_to_graph("rel_1", builder.compile())
    
    facts = [
        Fact(target_path="a", resolved_value=1, final_confidence=1.0),
        Fact(target_path="b", resolved_value=3, final_confidence=1.0) # This causes the AND to fail
    ]
    
    reasoning_graph = generate_reasoning_graph(base_context, rule_graph, facts)
    
    conclusion = next(n for n in reasoning_graph.nodes.values() if n.type == "conclusion")
    assert conclusion.data["overall_passed"] is False


def test_engine_fails_closed_on_missing_data(base_context: EvaluationContext):
    builder = DomainBuilder("Test Domain").require(Rule("target.value").gte(10))
    rule_graph = compile_release_to_graph("rel_1", builder.compile())
    
    facts: list[Fact] = [] # Missing data!
    
    reasoning_graph = generate_reasoning_graph(base_context, rule_graph, facts)
    
    conclusion = next(n for n in reasoning_graph.nodes.values() if n.type == "conclusion")
    assert conclusion.data["overall_passed"] is False
    assert conclusion.computed_confidence == 0.0 # Proves the fail-closed confidence zeroing

def test_engine_evaluates_grant_max_budget_rule(base_context: EvaluationContext):
    """
    Specifically tests the <= operator mathematically, proving the bug fix works
    and that the engine is domain-agnostic (handling financial thresholds).
    """
    builder = DomainBuilder("Grant Domain").require(Rule("financial.requested_budget_usd").lte(50000))
    rule_graph = compile_release_to_graph("rel_1", builder.compile())
    
    # 1. Test passing case (exactly on threshold)
    passing_facts = [Fact(target_path="financial.requested_budget_usd", resolved_value=50000, final_confidence=1.0)]
    passing_graph = generate_reasoning_graph(base_context, rule_graph, passing_facts)
    passing_conclusion = next(n for n in passing_graph.nodes.values() if n.type == "conclusion")
    assert passing_conclusion.data["overall_passed"] is True
    
    # 2. Test failing case (over budget)
    failing_facts = [Fact(target_path="financial.requested_budget_usd", resolved_value=50001, final_confidence=1.0)]
    failing_graph = generate_reasoning_graph(base_context, rule_graph, failing_facts)
    failing_conclusion = next(n for n in failing_graph.nodes.values() if n.type == "conclusion")
    assert failing_conclusion.data["overall_passed"] is False

def test_ambiguity_protocol_halts_evaluation(base_context: EvaluationContext):
    """
    Tests the Epistemic 'Ambiguity Protocol'. 
    If a Fact is resolved with 'needs_human_review' due to messy/ambiguous evidence,
    the rule must halt, avoiding a 0% fail-closed conclusion.
    """
    builder = DomainBuilder("Test Domain").require(Rule("academic.completed_majors").includes("Philosophy"))
    rule_graph = compile_release_to_graph("rel_1", builder.compile())
    
    # Simulate the Extractor/Conflict Engine flagging a messy email concession
    ambiguous_fact = Fact(
        target_path="academic.completed_majors",
        resolved_value=None,
        status="needs_human_review", 
        final_confidence=0.5
    )
    
    reasoning_graph = generate_reasoning_graph(base_context, rule_graph, [ambiguous_fact])
    
    conclusion = next(n for n in reasoning_graph.nodes.values() if n.type == "conclusion")
    
    # The rule evaluator should recognize the 'needs_human_review' sentinel
    # and propagate it to the conclusion rather than strictly failing.
    assert conclusion.data["overall_passed"] == "NEEDS_MANUAL_REVIEW"
