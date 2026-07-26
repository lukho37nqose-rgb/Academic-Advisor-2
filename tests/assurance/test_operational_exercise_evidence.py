from tools.validate_operational_exercise import validate_operational_exercise


def _record() -> dict[str, object]:
    return {
        "exercise_id": "recovery-synthetic-2026-07-26",
        "exercise_type": "backup_restore",
        "environment": "isolated-recovery",
        "performed_at": "2026-07-26T10:00:00+02:00",
        "operator_reference": "operator-ref-42",
        "result": "PASS",
        "duration_seconds": 420,
        "evidence_location": "institutional-evidence://recovery/2026-07-26",
        "evidence_references": ["change-record-123", "recovery-log-456"],
    }


def test_operational_exercise_evidence_accepts_complete_redacted_record() -> None:
    assert validate_operational_exercise(_record()) == []


def test_operational_exercise_evidence_requires_follow_up_for_blocked_drill() -> None:
    record = _record()
    record["result"] = "BLOCKED"

    errors = validate_operational_exercise(record)

    assert any("follow_up_owner" in error for error in errors)


def test_operational_exercise_evidence_rejects_credential_material() -> None:
    record = _record()
    record["access_token"] = "Bearer example-credential"

    errors = validate_operational_exercise(record)

    assert any("prohibited" in error or "credential" in error for error in errors)
