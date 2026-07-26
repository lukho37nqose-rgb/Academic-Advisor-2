from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.adapters.system_record_import import (
    SystemRecordImportContract,
    SystemRecordImportError,
    preview_system_record_csv,
    reconcile_system_record_previews,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "pilot" / "synthetic" / "system_record_contract.json"
CSV_PATH = ROOT / "pilot" / "synthetic" / "system_records.csv"


def _contract() -> SystemRecordImportContract:
    return SystemRecordImportContract.model_validate(
        json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    )


def test_system_record_preview_is_valid_and_excludes_values_from_summary() -> None:
    preview = preview_system_record_csv(CSV_PATH.read_bytes(), _contract())

    assert preview.is_valid is True
    assert preview.accepted_record_count == 2
    assert preview.rejected_row_count == 0
    assert preview.model_dump()["accepted_record_count"] == 2
    assert "records" not in preview.model_dump()
    records = preview.require_valid_records()
    assert records[0].evidence_payload(_contract())["fields"] == {
        "registration.is_active": True,
        "academic.completed_credits": 120,
        "account.has_administrative_block": False,
    }


def test_invalid_rows_block_all_record_materialisation() -> None:
    preview = preview_system_record_csv(
        b"record_identifier,record_version,as_of_date,active_registration,completed_credits,administrative_block\n"
        b"subject-1,1,2026-01-15,true,one-hundred,false\n"
        b"subject-1,2,2026-01-15,true,120,false\n",
        _contract(),
    )

    assert preview.is_valid is False
    assert preview.accepted_record_count == 0
    assert preview.rejected_row_count == 2
    with pytest.raises(SystemRecordImportError):
        preview.require_valid_records()


def test_reconciliation_flags_additions_changes_and_removals() -> None:
    contract = _contract()
    previous = preview_system_record_csv(CSV_PATH.read_bytes(), contract)
    candidate = preview_system_record_csv(
        b"record_identifier,record_version,as_of_date,active_registration,completed_credits,administrative_block\n"
        b"synthetic-subject-eligible,2,2026-01-16,true,132,false\n"
        b"synthetic-subject-new,1,2026-01-16,true,96,false\n",
        contract,
    )

    reconciliation = reconcile_system_record_previews(previous, candidate)

    assert reconciliation.requires_human_approval is True
    assert reconciliation.added_record_count == 1
    assert reconciliation.changed_record_count == 1
    assert reconciliation.removed_record_count == 1
    assert reconciliation.changed_subject_ids == ["synthetic-subject-eligible"]
    assert reconciliation.removed_subject_ids == ["synthetic-subject-below-threshold"]


def test_system_record_import_command_writes_no_subject_values(tmp_path: Path) -> None:
    output = tmp_path / "preview.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.adapters.system_record_import",
            "--contract",
            str(CONTRACT_PATH),
            "--csv",
            str(CSV_PATH),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["accepted_record_count"] == 2
    assert "records" not in summary
