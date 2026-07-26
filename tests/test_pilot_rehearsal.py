from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.sdk.pilot_rehearsal import PilotRehearsalSuite, run_pilot_rehearsal


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "pilot" / "synthetic" / "progression_policy.json"
SUITE_PATH = ROOT / "pilot" / "synthetic" / "progression_cases.json"


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_synthetic_pilot_rehearsal_is_repeatable_and_covers_safety_paths() -> None:
    policy = _load_json(POLICY_PATH)
    suite = PilotRehearsalSuite.model_validate(_load_json(SUITE_PATH))

    first_report = run_pilot_rehearsal(policy, suite)
    second_report = run_pilot_rehearsal(policy, suite)

    assert first_report.model_dump() == second_report.model_dump()
    assert first_report.all_cases_passed is True
    assert [case.actual_decision for case in first_report.cases] == [
        "ELIGIBLE",
        "INELIGIBLE",
        "INELIGIBLE",
        "NEEDS_MANUAL_REVIEW",
    ]
    assert all(len(case.trace_sha256) == 64 for case in first_report.cases)


def test_pilot_rehearsal_command_writes_a_machine_readable_report(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.sdk.pilot_rehearsal",
            "--policy",
            str(POLICY_PATH),
            "--suite",
            str(SUITE_PATH),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["all_cases_passed"] is True
    assert report["policy_sha256"]
