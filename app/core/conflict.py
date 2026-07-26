"""
The Conflict Engine.

Resolves competing Claims into canonical Facts. 
This is essential for appeals, auditing, and dealing with messy institutional data
(e.g., when a user form contradicts a system API).
"""

from typing import List, Dict, Any, Tuple
from collections import defaultdict
from .models import Claim, Fact

def _resolve_claims_for_target(target_path: str, claims: List[Claim]) -> Fact:
    """
    Takes a list of Claims pointing to the exact same target_path and resolves them.
    Currently uses a simplified weighted-majority rules engine.
    In a fully mature system, this would use proper Bayesian updating.
    """
    
    if not claims:
        raise ValueError(f"Cannot resolve Fact for {target_path} without claims.")
        
    # Group claims by their asserted value (converted to string for reliable hashing in this demo)
    value_scores: Dict[str, float] = defaultdict(float)
    value_map: Dict[str, Any] = {}
    claim_groups: Dict[str, List[Claim]] = defaultdict(list)
    
    # Ambiguity Protocol Check: If any high-trust claim requests manual review, the fact inherits it
    needs_review = False
    
    for claim in claims:
        if claim.status == "needs_human_review":
            needs_review = True
            
        key = str(claim.asserted_value).lower().strip()
        value_map[key] = claim.asserted_value
        claim_groups[key].append(claim)
        
        # The weight of a claim is its extraction confidence * the trust level of the source
        weight = claim.extraction_confidence * claim.source_trust_level
        value_scores[key] += weight
        
    # Find the winning value
    winning_key = max(value_scores.items(), key=lambda x: x[1])[0]
    winning_value = value_map[winning_key]
    winning_claims = claim_groups[winning_key]
    losing_claims = [c for c in claims if c not in winning_claims]
    
    # Calculate final confidence
    total_weight = sum(value_scores.values())
    winning_weight = value_scores[winning_key]
    
    base_confidence = winning_weight / total_weight if total_weight > 0 else 0.0
    max_extraction_conf = max(c.extraction_confidence for c in winning_claims)
    
    final_confidence = min(base_confidence, max_extraction_conf)
    
    status = "needs_human_review" if needs_review else "resolved"
    
    return Fact(
        target_path=target_path,
        resolved_value=winning_value,
        status=status, # type: ignore
        final_confidence=final_confidence if not needs_review else 0.5, # Cap confidence on ambiguous facts
        supporting_claims=[c.id for c in winning_claims],
        rejected_claims=[c.id for c in losing_claims],
    )

def resolve_claims_to_facts(claims: List[Claim]) -> List[Fact]:
    """
    Groups all claims by target_path and runs the resolution logic for each.
    """
    claims_by_target: Dict[str, List[Claim]] = defaultdict(list)
    
    for claim in claims:
        claims_by_target[claim.target_path].append(claim)
        
    resolved_facts = []
    
    for target_path, target_claims in claims_by_target.items():
        fact = _resolve_claims_for_target(target_path, target_claims)
        resolved_facts.append(fact)
        
    return resolved_facts
