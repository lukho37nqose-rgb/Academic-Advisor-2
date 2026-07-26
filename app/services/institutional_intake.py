"""No-code institutional input models and deterministic policy-draft builder."""

import re
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


FactDataType = Literal["text", "number", "yes_no"]
RuleOperator = Literal[
    "equals",
    "does_not_equal",
    "at_least",
    "at_most",
    "greater_than",
    "less_than",
    "contains",
]

_JSON_SCHEMA_TYPES = {
    "text": "string",
    "number": "number",
    "yes_no": "boolean",
}
_EXPRESSION_OPERATORS = {
    "equals": "==",
    "does_not_equal": "!=",
    "at_least": ">=",
    "at_most": "<=",
    "greater_than": ">",
    "less_than": "<",
    "contains": "includes",
}
_ALLOWED_OPERATORS = {
    "text": {"equals", "does_not_equal", "contains"},
    "number": {"equals", "does_not_equal", "at_least", "at_most", "greater_than", "less_than"},
    "yes_no": {"equals", "does_not_equal"},
}


class InstitutionalFactInput(BaseModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=2, max_length=120)
    data_type: FactDataType


class InstitutionalRuleInput(BaseModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=2, max_length=180)
    fact_id: str = Field(min_length=1)
    operator: RuleOperator
    value: Any
    source_citation: str = Field(min_length=3, max_length=500)


class InstitutionalIntakeRequest(BaseModel):
    institution_name: str = Field(min_length=2, max_length=160)
    domain_name: str = Field(min_length=2, max_length=160)
    policy_name: str | None = Field(default=None, max_length=160)
    public_policy_guide: bool = True
    assistance_requests_enabled: bool = True
    support_response_target_hours: int = Field(default=48, ge=1, le=8760)
    decision_review_enabled: bool = False
    decision_review_response_target_hours: int | None = Field(default=None, ge=1, le=8760)
    support_privacy_notice_url: str | None = Field(default=None, max_length=500)
    offline_assistance_instructions: str | None = Field(default=None, max_length=1000)
    facts: list[InstitutionalFactInput] = Field(min_length=1, max_length=100)
    rules: list[InstitutionalRuleInput] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def require_human_casework_commitments(self) -> "InstitutionalIntakeRequest":
        if not self.assistance_requests_enabled and not self.decision_review_enabled:
            return self
        privacy_notice = self.support_privacy_notice_url.strip() if self.support_privacy_notice_url else ""
        offline_instructions = (
            self.offline_assistance_instructions.strip()
            if self.offline_assistance_instructions
            else ""
        )
        if not privacy_notice.startswith(("https://", "http://")):
            raise ValueError("Human casework requires a privacy notice URL.")
        if len(offline_instructions) < 10:
            raise ValueError("Human casework requires an assisted or offline contact route.")
        if self.decision_review_enabled and self.decision_review_response_target_hours is None:
            raise ValueError("Decision review requires a response target in hours.")
        return self


class BuiltInstitutionalInput(BaseModel):
    schema_definition: dict[str, Any]
    policy_payload: dict[str, Any]
    fact_count: int
    rule_count: int


class InstitutionalInputError(ValueError):
    pass


def _safe_identifier(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    identifier = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")
    return identifier or "field"


def _validated_value(rule: InstitutionalRuleInput, fact: InstitutionalFactInput) -> Any:
    if rule.operator not in _ALLOWED_OPERATORS[fact.data_type]:
        raise InstitutionalInputError(
            f"'{rule.operator}' cannot be used with the {fact.data_type} fact '{fact.label}'."
        )
    if fact.data_type == "text":
        if not isinstance(rule.value, str) or not rule.value.strip():
            raise InstitutionalInputError(f"Rule '{rule.label}' needs a non-empty text value.")
        return rule.value.strip()
    if fact.data_type == "number":
        if isinstance(rule.value, bool) or not isinstance(rule.value, (int, float)):
            raise InstitutionalInputError(f"Rule '{rule.label}' needs a numeric value.")
        return rule.value
    if not isinstance(rule.value, bool):
        raise InstitutionalInputError(f"Rule '{rule.label}' needs a yes/no value.")
    return rule.value


def build_institutional_input(request: InstitutionalIntakeRequest) -> BuiltInstitutionalInput:
    """Compile guided administrator input into the runtime's neutral policy form."""
    fact_ids = [fact.id for fact in request.facts]
    rule_ids = [rule.id for rule in request.rules]
    if len(set(fact_ids)) != len(fact_ids):
        raise InstitutionalInputError("Every fact needs a unique form identifier.")
    if len(set(rule_ids)) != len(rule_ids):
        raise InstitutionalInputError("Every rule needs a unique form identifier.")

    fact_paths: dict[str, str] = {}
    schema_properties: dict[str, Any] = {}
    used_paths: set[str] = set()
    for fact in request.facts:
        identifier = _safe_identifier(fact.label)
        suffix = 2
        while identifier in used_paths:
            identifier = f"{_safe_identifier(fact.label)}_{suffix}"
            suffix += 1
        used_paths.add(identifier)
        fact_paths[fact.id] = f"facts.{identifier}"
        schema_properties[identifier] = {
            "type": _JSON_SCHEMA_TYPES[fact.data_type],
            "title": fact.label.strip(),
        }

    facts_by_id = {fact.id: fact for fact in request.facts}
    compiled_rules: list[dict[str, Any]] = []
    for rule in request.rules:
        referenced_fact = facts_by_id.get(rule.fact_id)
        if referenced_fact is None:
            raise InstitutionalInputError(f"Rule '{rule.label}' refers to an unknown fact.")
        compiled_rules.append(
            {
                "id": f"rule_{_safe_identifier(rule.id)}",
                "label": rule.label.strip(),
                "target": fact_paths[referenced_fact.id],
                "condition": _EXPRESSION_OPERATORS[rule.operator],
                "value": _validated_value(rule, referenced_fact),
                "source_citation": rule.source_citation.strip(),
            }
        )

    root = compiled_rules[0] if len(compiled_rules) == 1 else {
        "id": "root_all_conditions",
        "label": f"All requirements for {request.domain_name.strip()}",
        "operator": "AND",
        "children": compiled_rules,
    }
    return BuiltInstitutionalInput(
        schema_definition={
            "type": "object",
            "properties": {"facts": {"type": "object", "properties": schema_properties}},
            "access": {
                "public_policy_guide": request.public_policy_guide,
                "assistance_requests_enabled": request.assistance_requests_enabled,
                "support_response_target_hours": (
                    request.support_response_target_hours if request.assistance_requests_enabled else None
                ),
                "decision_review_enabled": request.decision_review_enabled,
                "decision_review_response_target_hours": (
                    request.decision_review_response_target_hours if request.decision_review_enabled else None
                ),
                "support_privacy_notice_url": (
                    request.support_privacy_notice_url.strip()
                    if (request.assistance_requests_enabled or request.decision_review_enabled)
                    and request.support_privacy_notice_url
                    else None
                ),
                "offline_assistance_instructions": (
                    request.offline_assistance_instructions.strip()
                    if (request.assistance_requests_enabled or request.decision_review_enabled)
                    and request.offline_assistance_instructions
                    else None
                ),
            },
        },
        policy_payload={"root": root},
        fact_count=len(request.facts),
        rule_count=len(request.rules),
    )
