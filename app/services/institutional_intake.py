"""No-code institutional input models and deterministic policy-draft builder."""

import re
import unicodedata
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, model_validator


FactDataType = Literal["text", "number", "yes_no"]
SubjectPositionType = Literal[
    "curriculum",
    "assessment_eligibility",
    "eligibility",
    "institutional_standing",
    "other",
]
DecisionAutomationMode = Literal["automatic", "human_confirmation_required"]
PolicyGroupOperator = Literal["all", "any", "not"]
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


class InstitutionalRuleGroupInput(BaseModel):
    """A named, no-code group of conditions or other groups.

    The simple intake screen supplies the root group automatically. This model
    lets an approved future advanced editor express cited exception paths without
    exposing the engine's JSON representation to staff.
    """

    id: str = Field(min_length=1)
    label: str = Field(min_length=2, max_length=180)
    operator: PolicyGroupOperator
    children: list[str] = Field(min_length=1, max_length=100)


class InstitutionalIntakeRequest(BaseModel):
    institution_name: str = Field(min_length=2, max_length=160)
    domain_name: str = Field(min_length=2, max_length=160)
    governed_person_label: str = Field(
        default="person",
        min_length=2,
        max_length=80,
        validation_alias=AliasChoices("governed_person_label", "subject_label", "student_label"),
    )
    position_collection_label: str | None = Field(default=None, min_length=2, max_length=120)
    subject_position_type: SubjectPositionType = Field(
        default="other",
        validation_alias=AliasChoices("subject_position_type", "student_position_type"),
    )
    subject_position_label: str | None = Field(
        default=None,
        min_length=2,
        max_length=120,
        validation_alias=AliasChoices("subject_position_label", "student_position_label"),
    )
    # Older API clients did not send an automation choice. The guided UI always
    # sends one and defaults it to human confirmation; retain compatibility here.
    automation_mode: DecisionAutomationMode = "automatic"
    policy_name: str | None = Field(default=None, max_length=160)
    public_policy_guide: bool = True
    assistance_requests_enabled: bool = True
    support_response_target_hours: int = Field(default=48, ge=1, le=8760)
    decision_review_enabled: bool = False
    decision_review_response_target_hours: int | None = Field(default=None, ge=1, le=8760)
    support_privacy_notice_url: str | None = Field(default=None, max_length=500)
    offline_assistance_instructions: str | None = Field(default=None, max_length=1000)
    casework_primary_group: str = Field(default="Institutional casework team", min_length=3, max_length=160)
    casework_fallback_group: str | None = Field(default=None, max_length=160)
    casework_escalation_after_hours: int = Field(default=72, ge=1, le=8760)
    facts: list[InstitutionalFactInput] = Field(min_length=1, max_length=100)
    rules: list[InstitutionalRuleInput] = Field(min_length=1, max_length=100)
    root_operator: Literal["all", "any"] = "all"
    rule_groups: list[InstitutionalRuleGroupInput] = Field(default_factory=list, max_length=100)
    root_group_id: str | None = Field(default=None, min_length=1)

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
        if self.automation_mode == "human_confirmation_required" and not self.decision_review_enabled:
            raise ValueError("A human-confirmation decision requires decision review to be enabled.")
        return self


class BuiltInstitutionalInput(BaseModel):
    schema_definition: dict[str, Any]
    policy_payload: dict[str, Any]
    fact_count: int
    rule_count: int
    rule_group_count: int


class InstitutionalInputError(ValueError):
    pass


def _safe_identifier(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    identifier = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")
    return identifier or "field"


def _plain_display_label(value: str | None, default: str) -> str:
    label = " ".join((value or default).split())
    if not label:
        label = default
    if any(character in label for character in "<>{}"):
        raise InstitutionalInputError("Presentation labels must be plain text.")
    return label


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
    governed_person_label = _plain_display_label(request.governed_person_label, "person")
    position_collection_label = _plain_display_label(request.position_collection_label, "current positions")
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
    compiled_rules: dict[str, dict[str, Any]] = {}
    for rule in request.rules:
        referenced_fact = facts_by_id.get(rule.fact_id)
        if referenced_fact is None:
            raise InstitutionalInputError(f"Rule '{rule.label}' refers to an unknown fact.")
        compiled_rules[rule.id] = {
            "id": f"rule_{_safe_identifier(rule.id)}",
            "label": rule.label.strip(),
            "target": fact_paths[referenced_fact.id],
            "condition": _EXPRESSION_OPERATORS[rule.operator],
            "value": _validated_value(rule, referenced_fact),
            "source_citation": rule.source_citation.strip(),
        }

    groups = {group.id: group for group in request.rule_groups}
    if len(groups) != len(request.rule_groups):
        raise InstitutionalInputError("Every condition group needs a unique form identifier.")
    if set(groups).intersection(compiled_rules):
        raise InstitutionalInputError("Condition group identifiers cannot duplicate condition identifiers.")

    expression_operators = {"all": "AND", "any": "OR", "not": "NOT"}

    def build_group(group_id: str, ancestors: set[str]) -> dict[str, Any]:
        if group_id in ancestors:
            raise InstitutionalInputError("Condition groups cannot contain a circular reference.")
        group = groups.get(group_id)
        if group is None:
            raise InstitutionalInputError("The selected condition group does not exist.")
        if group.operator == "not" and len(group.children) != 1:
            raise InstitutionalInputError(f"Exception group '{group.label}' must contain exactly one condition.")
        children: list[dict[str, Any]] = []
        for child_id in group.children:
            if child_id in compiled_rules:
                children.append(compiled_rules[child_id])
            elif child_id in groups:
                children.append(build_group(child_id, ancestors | {group_id}))
            else:
                raise InstitutionalInputError(f"Condition group '{group.label}' refers to an unknown item.")
        return {
            "id": f"group_{_safe_identifier(group.id)}",
            "label": group.label.strip(),
            "operator": expression_operators[group.operator],
            "children": children,
        }

    if request.root_group_id:
        root = build_group(request.root_group_id, set())
    elif len(compiled_rules) == 1:
        root = next(iter(compiled_rules.values()))
    else:
        root = {
            "id": f"root_{request.root_operator}_conditions",
            "label": f"{'All' if request.root_operator == 'all' else 'Any'} route for {request.domain_name.strip()}",
            "operator": expression_operators[request.root_operator],
            "children": list(compiled_rules.values()),
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
            "casework": {
                "primary_group": request.casework_primary_group.strip(),
                "fallback_group": request.casework_fallback_group.strip() if request.casework_fallback_group else None,
                "escalation_after_hours": request.casework_escalation_after_hours,
            },
            "presentation": {
                "governed_person_label": governed_person_label,
                "position_collection_label": position_collection_label,
            },
            "subject_position": {
                "type": request.subject_position_type,
                "label": (
                    request.subject_position_label.strip()
                    if request.subject_position_label
                    else request.domain_name.strip()
                ),
            },
            "decision_safety": {"automation_mode": request.automation_mode},
        },
        policy_payload={"root": root},
        fact_count=len(request.facts),
        rule_count=len(request.rules),
        rule_group_count=len(request.rule_groups),
    )
