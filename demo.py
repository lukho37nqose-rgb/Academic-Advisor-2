"""
Developer Experience Demo.

If you are an engineer from an ERP vendor or University IT department evaluating this platform,
this script demonstrates the entire architecture in a single, executable flow.

It demonstrates:
1. Policy as Code (using the Policy SDK)
2. Compiling the static RuleGraph
3. Using Adapters to ingest external data
4. Executing the Reasoning Engine
5. The Ambiguity Protocol (routing messy evidence for human review)
"""

import json
import asyncio
from app.sdk.policy import DomainBuilder, Rule
from app.core.compiler import compile_release_to_graph
from app.adapters.evidence import LegacyERPAdapter
from app.core.models import Claim
from app.core.conflict import resolve_claims_to_facts
from app.core.engine import generate_reasoning_graph
from app.core.models import EvaluationContext

async def main():
    print("=== Institutional Reasoning Engine DX Demo ===\n")
    
    # ---------------------------------------------------------
    # 1. Author Policy using the Python SDK
    # ---------------------------------------------------------
    print("[1] Authoring Policy via SDK...")
    domain = DomainBuilder("Admissions 2027")
    
    domain.require(
        Rule("academic.gpa", "Minimum GPA", "Admissions Policy v2").gte(3.0)
    )
    domain.any_of(
        Rule("academic.sat_score", "SAT Minimum").gte(1200),
        Rule("academic.act_score", "ACT Minimum").gte(25)
    )
    
    raw_payload = domain.compile()
    print("    -> Compiled to strict JSON schema.")


    # ---------------------------------------------------------
    # 2. Compile Static RuleGraph (The Governance Publish Gate)
    # ---------------------------------------------------------
    print("[2] Compiling RuleGraph (Bytecode)...")
    rule_graph = compile_release_to_graph("rel_2027_v1", raw_payload)
    print(f"    -> Static Graph ID: {rule_graph.id} (Nodes: {len(raw_payload['root']['children'])})")


    # ---------------------------------------------------------
    # 3. Ingest Data via Adapters
    # ---------------------------------------------------------
    print("[3] Ingesting Data from Legacy ERP Adapter...")
    adapter = LegacyERPAdapter()
    
    erp_payload = {
        "system_identifier": "banner_prod_01",
        "academic": {
            "gpa": 3.8,
            "sat_score": 1400,
            "act_score": None
        }
    }
    evidence = await adapter.ingest(subject_id="applicant_99", raw_payload=erp_payload)
    print(f"    -> Evidence secured with SHA-256: {evidence.cryptographic_hash}")


    # ---------------------------------------------------------
    # 4. Extract Claims & Resolve Facts (Epistemological layer)
    # ---------------------------------------------------------
    print("[4] Resolving Claims to Facts (Conflict Engine)...")
    
    # We mock the extractor here, but crucially include an ambiguous claim!
    # Imagine a user uploaded an email from a professor instead of a clean transcript.
    claims = [
        Claim(evidence_id=evidence.id, target_path="academic.gpa", asserted_value=3.8, extraction_confidence=1.0, source_trust_level=0.9),
        Claim(evidence_id=evidence.id, target_path="academic.sat_score", asserted_value="needs_human_review", extraction_confidence=0.5, source_trust_level=0.5)
    ]
    
    # NOTE: Our logic dictates that messy inputs from the LLM indicate Needs Review.
    # To demonstrate the fail-closed Ambiguity Protocol, we manually mark one claim as ambiguous:
    claims[1].asserted_value = "needs_human_review"
    
    facts = resolve_claims_to_facts(claims)
    print(f"    -> Resolved {len(facts)} canonical facts.")


    # ---------------------------------------------------------
    # 5. Execute the Dynamic Reasoning Engine
    # ---------------------------------------------------------
    print("[5] Executing Reasoning Engine...")
    context = EvaluationContext(tenant_id="tenant_demo", subject_id="applicant_99", domain_id="Admissions 2027", release_version="rel_2027_v1")
    reasoning_graph = generate_reasoning_graph(context=context, rule_graph=rule_graph, facts_list=facts)


    # ---------------------------------------------------------
    # 6. Inspect the Output
    # ---------------------------------------------------------
    print("\n=== FINAL REASONING GRAPH TRACE ===")
    
    # Find the conclusion
    conclusion = next(n for n in reasoning_graph.nodes.values() if n.type == "conclusion")
    print(f"DECISION: {conclusion.data['overall_passed']}")
    print(f"CONFIDENCE: {conclusion.computed_confidence}\n")
    
    print("DETAILED GRAPH NODES (Audit Trail):")
    for node_id, node in reasoning_graph.nodes.items():
        if node.type == "rule_evaluation":
            status = str(node.data.get('passed'))
            if status == "True": status = "PASS"
            if status == "False": status = "FAIL"
            print(f"  [{status}] {node.label} (Confidence: {node.computed_confidence})")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
