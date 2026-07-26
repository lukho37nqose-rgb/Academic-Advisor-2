"""Validate a redacted record of an institution-operated resilience exercise.

The tool validates the *evidence record*, not the backup or incident response
itself. Its purpose is to stop a pilot team treating an undocumented drill as a
completed control or putting credentials and personal data into a repository.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


EXERCISE_TYPES = frozenset({
    "backup_restore",
    "identity_revocation",
    "incident_response",
    "dead_letter_recovery",
    "signing_key_rotation",
})
RESULTS = frozenset({"PASS", "FAIL", "BLOCKED"})
_PROHIBITED_KEY_PATTERN = re.compile(r"(password|secret|token|private.?key|raw.?evidence)", re.IGNORECASE)
_PROHIBITED_VALUE_PATTERN = re.compile(r"(-----BEGIN .*PRIVATE KEY-----|Bearer\s+|AKIA[0-9A-Z]{16})")


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _contains_sensitive_data(value: object, *, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, nested_value in value.items():
            key_string = str(key)
            nested_path = f"{path}.{key_string}"
            if _PROHIBITED_KEY_PATTERN.search(key_string):
                errors.append(f"{nested_path} uses a prohibited sensitive-data field name.")
            errors.extend(_contains_sensitive_data(nested_value, path=nested_path))
    elif isinstance(value, list):
        for index, nested_value in enumerate(value):
            errors.extend(_contains_sensitive_data(nested_value, path=f"{path}[{index}]"))
    elif isinstance(value, str) and _PROHIBITED_VALUE_PATTERN.search(value):
        errors.append(f"{path} appears to contain a credential or private key.")
    return errors


def validate_operational_exercise(record: object) -> list[str]:
    """Return all schema and redaction errors for a proposed exercise record."""
    if not isinstance(record, dict):
        return ["The exercise record must be a JSON object."]

    errors: list[str] = []
    required_string_fields = (
        "exercise_id",
        "exercise_type",
        "environment",
        "performed_at",
        "operator_reference",
        "result",
        "evidence_location",
    )
    for field in required_string_fields:
        if not _is_non_empty_string(record.get(field)):
            errors.append(f"{field} must be a non-empty string.")

    if record.get("exercise_type") not in EXERCISE_TYPES:
        errors.append("exercise_type is not a supported operational exercise.")
    if record.get("result") not in RESULTS:
        errors.append("result must be PASS, FAIL, or BLOCKED.")

    performed_at = record.get("performed_at")
    if isinstance(performed_at, str):
        try:
            parsed = datetime.fromisoformat(performed_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                errors.append("performed_at must include a timezone.")
        except ValueError:
            errors.append("performed_at must be an ISO 8601 timestamp.")

    duration_seconds = record.get("duration_seconds")
    if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int) or duration_seconds < 0:
        errors.append("duration_seconds must be a non-negative whole number.")

    evidence_references = record.get("evidence_references")
    if (
        not isinstance(evidence_references, list)
        or not evidence_references
        or not all(_is_non_empty_string(reference) for reference in evidence_references)
    ):
        errors.append("evidence_references must contain at least one redacted reference.")

    if record.get("result") in {"FAIL", "BLOCKED"} and not _is_non_empty_string(record.get("follow_up_owner")):
        errors.append("A failed or blocked exercise requires follow_up_owner.")

    errors.extend(_contains_sensitive_data(record))
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a redacted operational exercise JSON record.")
    parser.add_argument("record", type=Path)
    args = parser.parse_args()
    try:
        record: Any = json.loads(args.record.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not read an operational exercise record: {exc}") from exc
    errors = validate_operational_exercise(record)
    if errors:
        raise SystemExit("Operational exercise record is invalid:\n- " + "\n- ".join(errors))
    print("Operational exercise record is valid and contains no obvious credential fields.")


if __name__ == "__main__":
    main()
