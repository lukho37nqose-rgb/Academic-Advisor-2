"""Run deterministic, fixture-backed pilot rehearsals.

This module is deliberately independent from any institution's source material.
It turns an approved future pilot corpus into a stable set of golden cases, runs
them through the production compiler and evaluator, and emits a canonical report
that can be retained with pilot evidence.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.compiler import compile_release_to_graph
from app.core.engine import generate_reasoning_graph
from app.core.models import EvaluationContext, Fact, ReasoningGraph


Decision = Literal["ELIGIBLE", "INELIGIBLE", "NEEDS_MANUAL_REVIEW"]


class GoldenFact(BaseModel):
    """A resolved fact supplied to one golden case, never live subject data."""

    id: str
    target_path: str
    resolved_value: Any
    final_confidence: float = Field(ge=0.0, le=1.0)
    status: Literal["resolved", "needs_human_review"] = "resolved"
    supporting_claims: list[str] = Field(default_factory=list)
    rejected_claims: list[str] = Field(default_factory=list)

    def to_fact(self) -> Fact:
        return Fact(**self.model_dump())


class GoldenCase(BaseModel):
    """A known expected outcome for an immutable synthetic or approved corpus."""

    id: str
    description: str
    subject_reference: str
    facts: list[GoldenFact] = Field(default_factory=list)
    expected_decision: Decision


class PilotRehearsalSuite(BaseModel):
    """The non-policy input envelope for a deterministic rehearsal run."""

    suite_id: str
    description: str
    release_id: str
    tenant_id: str
    domain_id: str
    release_version: str
    policy_as_of_date: datetime.date
    evaluation_timestamp: str
    cases: list[GoldenCase] = Field(min_length=1)


class GoldenCaseResult(BaseModel):
    id: str
    description: str
    subject_reference: str
    expected_decision: Decision
    actual_decision: Decision
    passed: bool
    input_sha256: str
    trace_sha256: str
    evaluated_rules: int


class PilotRehearsalReport(BaseModel):
    format_version: Literal["1.0"] = "1.0"
    suite_id: str
    suite_description: str
    release_id: str
    release_version: str
    policy_as_of_date: str
    policy_sha256: str
    all_cases_passed: bool
    cases: list[GoldenCaseResult]


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=_json_default,
    )


def _json_default(value: Any) -> Any:
    """Encode typed trace metadata in the same stable form used in JSON APIs."""

    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    raise TypeError(f"Cannot canonicalise {type(value).__name__} in a rehearsal report.")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _decision_from_graph(reasoning_graph: ReasoningGraph) -> Decision:
    conclusion = next(
        (node for node in reasoning_graph.nodes.values() if node.type == "conclusion"),
        None,
    )
    if conclusion is None:
        raise ValueError("Evaluation trace did not contain a conclusion node.")

    outcome = conclusion.data.get("overall_passed")
    if outcome == "NEEDS_MANUAL_REVIEW":
        return "NEEDS_MANUAL_REVIEW"
    if outcome is True:
        return "ELIGIBLE"
    return "INELIGIBLE"


def _trace_payload(reasoning_graph: ReasoningGraph) -> dict[str, Any]:
    """Exclude generated trace IDs while retaining all decision-bearing data."""

    return {
        "nodes": [
            {
                "id": node.id,
                "type": node.type,
                "label": node.label,
                "data": node.data,
                "computed_confidence": node.computed_confidence,
            }
            for node in sorted(reasoning_graph.nodes.values(), key=lambda item: item.id)
        ],
        "edges": [
            {
                "source_id": edge.source_id,
                "target_id": edge.target_id,
                "relation": edge.relation,
                "weight": edge.weight,
            }
            for edge in sorted(
                reasoning_graph.edges,
                key=lambda item: (item.source_id, item.target_id, item.relation, item.weight),
            )
        ],
    }


def run_pilot_rehearsal(
    policy_payload: dict[str, Any], suite: PilotRehearsalSuite
) -> PilotRehearsalReport:
    """Compile one policy and evaluate every fixture case without persistence."""

    rule_graph = compile_release_to_graph(suite.release_id, policy_payload)
    results: list[GoldenCaseResult] = []

    for case in suite.cases:
        context = EvaluationContext(
            tenant_id=suite.tenant_id,
            subject_id=case.subject_reference,
            domain_id=suite.domain_id,
            release_version=suite.release_version,
            policy_as_of_date=suite.policy_as_of_date,
            timestamp=suite.evaluation_timestamp,
        )
        reasoning_graph = generate_reasoning_graph(
            context,
            rule_graph,
            [fact.to_fact() for fact in case.facts],
        )
        actual_decision = _decision_from_graph(reasoning_graph)
        results.append(
            GoldenCaseResult(
                id=case.id,
                description=case.description,
                subject_reference=case.subject_reference,
                expected_decision=case.expected_decision,
                actual_decision=actual_decision,
                passed=actual_decision == case.expected_decision,
                input_sha256=_sha256(case.model_dump()),
                trace_sha256=_sha256(_trace_payload(reasoning_graph)),
                evaluated_rules=sum(
                    node.type == "rule_evaluation"
                    for node in reasoning_graph.nodes.values()
                ),
            )
        )

    return PilotRehearsalReport(
        suite_id=suite.suite_id,
        suite_description=suite.description,
        release_id=suite.release_id,
        release_version=suite.release_version,
        policy_as_of_date=suite.policy_as_of_date.isoformat(),
        policy_sha256=_sha256(policy_payload),
        all_cases_passed=all(result.passed for result in results),
        cases=results,
    )


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object and reject arrays or scalar values at the boundary."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return value


def write_report(path: Path, report: PilotRehearsalReport) -> None:
    """Atomically replace a report so interrupted runs leave prior evidence intact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(report.model_dump(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run fixture-backed deterministic pilot rehearsal cases."
    )
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    suite = PilotRehearsalSuite.model_validate(load_json_object(args.suite))
    report = run_pilot_rehearsal(load_json_object(args.policy), suite)
    serialized_report = json.dumps(report.model_dump(), indent=2, sort_keys=True)

    if args.output:
        write_report(args.output, report)
        print(f"Wrote pilot rehearsal report to {args.output}")
    else:
        print(serialized_report)

    return 0 if report.all_cases_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
