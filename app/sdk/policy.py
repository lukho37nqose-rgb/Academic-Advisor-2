import json
from typing import List, Dict, Any, Optional
import uuid

class Rule:
    """A single leaf node rule."""
    def __init__(self, target_path: str, label: Optional[str] = None, citation: Optional[str] = None):
        self.target_path = target_path
        self.label = label or f"Check {target_path}"
        self.condition: Optional[str] = None
        self.value: Optional[Any] = None
        self.citation: Optional[str] = citation
        
    def eq(self, value: Any, citation: Optional[str] = None):
        """Matches test usage of .eq() while maintaining backward compatibility with .equals()"""
        self.condition = "=="
        self.value = value
        if citation:
            self.citation = citation
        return self
        
    def equals(self, value: Any, citation: Optional[str] = None):
        return self.eq(value, citation)
        
    def neq(self, value: Any, citation: Optional[str] = None):
        self.condition = "!="
        self.value = value
        if citation:
            self.citation = citation
        return self
        
    def gte(self, value: float, citation: Optional[str] = None):
        self.condition = ">="
        self.value = value
        if citation:
            self.citation = citation
        return self

    def lte(self, value: float, citation: Optional[str] = None):
        self.condition = "<="
        self.value = value
        if citation:
            self.citation = citation
        return self

    def gt(self, value: float, citation: Optional[str] = None):
        self.condition = ">"
        self.value = value
        if citation:
            self.citation = citation
        return self

    def lt(self, value: float, citation: Optional[str] = None):
        self.condition = "<"
        self.value = value
        if citation:
            self.citation = citation
        return self

    def includes(self, value: Any, citation: Optional[str] = None):
        self.condition = "includes"
        self.value = value
        if citation:
            self.citation = citation
        return self
        
    def compile(self) -> Dict[str, Any]:
        return {
            "id": f"rule_{uuid.uuid4().hex[:8]}",
            "label": self.label,
            "target": self.target_path,
            "condition": self.condition,
            "value": self.value,
            "source_citation": self.citation
        }

class Branch:
    """A logical branch node (AND, OR, NOT)."""
    def __init__(self, operator: str, label: Optional[str] = None):
        if operator not in ["AND", "OR", "NOT"]:
            raise ValueError("Operator must be AND, OR, or NOT")
        self.operator = operator
        self.label = label or f"Logical {operator}"
        self._children: List[Any] = []
        
    def add(self, child):
        self._children.append(child)
        return self
        
    def compile(self) -> Dict[str, Any]:
        return {
            "id": f"branch_{uuid.uuid4().hex[:8]}",
            "label": self.label,
            "operator": self.operator,
            "children": [c.compile() for c in self._children]
        }

class DomainBuilder:
    """Entrypoint for building a Domain's RuleGraph payload."""
    def __init__(self, domain_name: str):
        self.domain_name = domain_name
        self.root = Branch("AND", label=f"{domain_name} Root Policy")
        
    def require(self, rule_or_branch):
        """Adds a requirement to the root AND branch."""
        self.root.add(rule_or_branch)
        return self
        
    def any_of(self, *rules_or_branches):
        """Creates an OR branch and adds it to the root."""
        or_branch = Branch("OR")
        for r in rules_or_branches:
            or_branch.add(r)
        self.root.add(or_branch)
        return self
        
    def compile(self) -> Dict[str, Any]:
        """Compiles the entire builder into the JSON payload expected by the Engine."""
        return {
            "domain_name": self.domain_name,
            "root": self.root.compile()
        }


# --- Example Usage ---
def create_academic_standing_policy():
    """
    Example of how a University Rule Author would define a policy using Python
    instead of writing raw JSON.
    """
    builder = DomainBuilder("Academic Standing")
    
    # Simple GPA requirement
    gpa_rule = Rule("academic.gpa", "Minimum GPA", "Student Handbook Section 4.1").gte(2.0)
    
    # Financial standing (no active holds)
    holds_rule = Rule("financial.holds", "No Financial Holds").eq([], citation="Bursar Policy 2023")
    
    # Either enrolled full-time or has a part-time waiver
    enrollment_or = Branch("OR", "Enrollment Status")
    full_time = Rule("academic.credits", "Full Time").gte(12)
    waiver = Rule("admin.waivers", "Part Time Waiver").includes("PT_WAIVER_2024")
    enrollment_or.add(full_time).add(waiver)
    
    # Combine them
    builder.require(gpa_rule)
    builder.require(holds_rule)
    builder.require(enrollment_or)
    
    return builder.compile()

