"""No-code policy composition remains deterministic and fail-closed."""

import pytest

from app.services.institutional_intake import (
    InstitutionalFactInput,
    InstitutionalInputError,
    InstitutionalIntakeRequest,
    InstitutionalRuleGroupInput,
    InstitutionalRuleInput,
    build_institutional_input,
)


def _request(**changes):
    data = {
        "institution_name": "Example University",
        "domain_name": "Programme eligibility",
        "assistance_requests_enabled": False,
        "facts": [
            InstitutionalFactInput(id="gpa", label="Grade point average", data_type="number"),
            InstitutionalFactInput(id="concession", label="Active concession", data_type="yes_no"),
        ],
        "rules": [
            InstitutionalRuleInput(id="minimum_gpa", label="Minimum GPA", fact_id="gpa", operator="at_least", value=3, source_citation="Handbook p. 10"),
            InstitutionalRuleInput(id="has_concession", label="Concession exists", fact_id="concession", operator="equals", value=True, source_citation="Committee rule p. 2"),
        ],
    }
    data.update(changes)
    return InstitutionalIntakeRequest(**data)


def test_no_code_builder_can_create_any_route_policy():
    built = build_institutional_input(_request(root_operator="any"))
    assert built.policy_payload["root"]["operator"] == "OR"
    assert len(built.policy_payload["root"]["children"]) == 2


def test_no_code_builder_records_a_subject_facing_position_category():
    built = build_institutional_input(
        _request(
            subject_position_type="assessment_eligibility",
            subject_position_label="DP eligibility",
        )
    )
    assert built.schema_definition["subject_position"] == {
        "type": "assessment_eligibility",
        "label": "DP eligibility",
    }


def test_no_code_builder_records_domain_presentation_language():
    built = build_institutional_input(
        _request(
            governed_person_label="applicant",
            position_collection_label="application positions",
        )
    )
    assert built.schema_definition["presentation"] == {
        "governed_person_label": "applicant",
        "position_collection_label": "application positions",
    }


def test_no_code_builder_rejects_non_plain_presentation_labels():
    with pytest.raises(InstitutionalInputError, match="plain text"):
        build_institutional_input(_request(governed_person_label="<student>"))


def test_no_code_builder_accepts_legacy_student_position_fields():
    built = build_institutional_input(
        _request(
            student_position_type="curriculum",
            student_position_label="Degree progression",
        )
    )
    assert built.schema_definition["subject_position"] == {
        "type": "curriculum",
        "label": "Degree progression",
    }


def test_no_code_builder_can_create_a_cited_exception_group():
    request = _request(
        root_group_id="eligible_or_concession",
        rule_groups=[
            InstitutionalRuleGroupInput(
                id="eligible_or_concession",
                label="Standard eligibility or approved concession",
                operator="any",
                children=["minimum_gpa", "has_concession"],
            ),
        ],
    )
    built = build_institutional_input(request)
    assert built.policy_payload["root"]["operator"] == "OR"
    assert built.rule_group_count == 1


def test_no_code_builder_rejects_circular_condition_groups():
    request = _request(
        root_group_id="first",
        rule_groups=[
            InstitutionalRuleGroupInput(id="first", label="First group", operator="all", children=["second"]),
            InstitutionalRuleGroupInput(id="second", label="Second group", operator="all", children=["first"]),
        ],
    )
    with pytest.raises(InstitutionalInputError, match="circular"):
        build_institutional_input(request)
