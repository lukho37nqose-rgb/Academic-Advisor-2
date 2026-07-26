"""
Policy Testing Framework (SDK).

Allows Rule Authors and Approvers to write unit tests for their releases.
Treats policy-as-code by ensuring that a RuleGraph evaluates predictably
against a known set of mock Facts before it is ever published.
"""

from typing import List, Dict, Any, Tuple
from app.core.models import Fact, RuleGraph, EvaluationContext
from app.core.engine import generate_reasoning_graph
from app.core.compiler import compile_release_to_graph
from app.sdk.policy import DomainBuilder

class PolicyTestCase:
    def __init__(self, name: str, mock_facts: List[Dict[str, Any]], expected_decision: bool):
        self.name = name
        self.expected_decision = expected_decision
        
        # Convert simple dictionaries into proper Fact objects with perfect confidence
        self.facts = []
        for fact_dict in mock_facts:
            for path, value in fact_dict.items():
                self.facts.append(
                    Fact(
                        target_path=path,
                        resolved_value=value,
                        final_confidence=1.0,
                        supporting_claims=["mock_claim"]
                    )
                )

class PolicyTestSuite:
    """Executes a suite of TestCases against a compiled RuleGraph."""
    
    def __init__(self, rule_graph: RuleGraph):
        self.rule_graph = rule_graph
        self.tests: List[PolicyTestCase] = []
        
    def add_test(self, test_case: PolicyTestCase):
        self.tests.append(test_case)
        
    def run(self) -> Tuple[bool, List[str]]:
        """Returns True if all tests pass, along with a report."""
        report = []
        all_passed = True
        
        for test in self.tests:
            context = EvaluationContext(
                tenant_id="test_runner",
                subject_id="mock_subject",
                domain_id="test_domain",
                release_version="test"
            )
            
            # Execute the Reasoning Engine in test mode
            reasoning_graph = generate_reasoning_graph(context, self.rule_graph, test.facts)
            
            # Find the conclusion
            final_node = next((n for n in reasoning_graph.nodes.values() if n.type == "conclusion"), None)
            actual_decision = final_node.data.get("overall_passed", False) if final_node else False
            
            if actual_decision == test.expected_decision:
                report.append(f"✅ PASS: {test.name}")
            else:
                report.append(f"❌ FAIL: {test.name} (Expected {test.expected_decision}, got {actual_decision})")
                all_passed = False
                
        return all_passed, report

# --- Example Usage (If run directly) ---
if __name__ == "__main__":
    from app.sdk.policy import Rule
    
    print("Running Policy SDK Tests...\n")
    
    # 1. Author a Policy
    builder = DomainBuilder("Admissions")
    builder.require(Rule("academic.gpa").gte(3.0))
    rule_graph = compile_release_to_graph("test_release", builder.compile())
    
    # 2. Build the Test Suite
    suite = PolicyTestSuite(rule_graph)
    
    suite.add_test(PolicyTestCase(
        name="Eligible Student",
        mock_facts=[{"academic.gpa": 3.5}],
        expected_decision=True
    ))
    
    suite.add_test(PolicyTestCase(
        name="Ineligible Student",
        mock_facts=[{"academic.gpa": 2.5}],
        expected_decision=False
    ))
    
    suite.add_test(PolicyTestCase(
        name="Missing Data (Should Fail Closed)",
        mock_facts=[],
        expected_decision=False
    ))
    
    # 3. Execute
    success, results = suite.run()
    for res in results:
        print(res)
        
    if not success:
        exit(1)
