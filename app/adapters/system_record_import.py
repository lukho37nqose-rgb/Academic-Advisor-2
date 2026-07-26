"""Validate one-way system-of-record exports before they reach decision inputs.

The adapter deliberately does not connect to, or write to, an institutional
system of record. It validates a CSV export against a reviewed mapping, retains
only an in-memory preview, and provides a reconciliation report for a human to
approve before downstream evidence ingestion is considered.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import io
import json
import math
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


RecordValueType = Literal["text", "integer", "number", "boolean", "date"]
_TARGET_PATH_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*$")
_BOOLEAN_VALUES = {
    "true": True,
    "false": False,
    "yes": True,
    "no": False,
    "1": True,
    "0": False,
}


class SystemRecordImportError(ValueError):
    """Raised when a preview is unsafe to materialise as downstream evidence."""


class SystemRecordFieldMapping(BaseModel):
    """A reviewed, no-code mapping from one source column to one fact path."""

    source_column: str = Field(min_length=1, max_length=160)
    target_path: str = Field(min_length=3, max_length=240)
    value_type: RecordValueType
    required: bool = True

    @field_validator("source_column", "target_path")
    @classmethod
    def trim_identifiers(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Mapping identifiers cannot be blank.")
        return trimmed

    @field_validator("target_path")
    @classmethod
    def validate_target_path(cls, value: str) -> str:
        if not _TARGET_PATH_PATTERN.fullmatch(value):
            raise ValueError("Target paths must use dot-separated ASCII identifiers.")
        return value


class SystemRecordImportContract(BaseModel):
    """An institution-approved CSV contract, independent of a vendor API."""

    format_version: Literal["1.0"] = "1.0"
    mapping_id: str = Field(min_length=3, max_length=120)
    source_system: str = Field(min_length=2, max_length=160)
    subject_identifier_column: str = Field(min_length=1, max_length=160)
    source_record_version_column: str = Field(min_length=1, max_length=160)
    source_as_of_date_column: str | None = Field(default=None, max_length=160)
    fields: list[SystemRecordFieldMapping] = Field(min_length=1, max_length=200)
    max_rows: int = Field(default=10_000, ge=1, le=100_000)
    max_bytes: int = Field(default=20_000_000, ge=1_024, le=200_000_000)

    @field_validator(
        "mapping_id",
        "source_system",
        "subject_identifier_column",
        "source_record_version_column",
        "source_as_of_date_column",
    )
    @classmethod
    def trim_contract_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Contract identifiers cannot be blank.")
        return trimmed

    @model_validator(mode="after")
    def validate_unique_columns_and_targets(self) -> "SystemRecordImportContract":
        source_columns = [field.source_column for field in self.fields]
        target_paths = [field.target_path for field in self.fields]
        if len(set(source_columns)) != len(source_columns):
            raise ValueError("Each mapped source column may be used only once.")
        if len(set(target_paths)) != len(target_paths):
            raise ValueError("Each mapped target path may be used only once.")
        reserved_columns = {self.subject_identifier_column, self.source_record_version_column}
        if self.source_as_of_date_column:
            reserved_columns.add(self.source_as_of_date_column)
        if len(reserved_columns) != 2 + int(self.source_as_of_date_column is not None):
            raise ValueError("Subject, version, and as-of columns must be distinct.")
        if reserved_columns.intersection(source_columns):
            raise ValueError("Identity and source-version columns cannot also be mapped as decision facts.")
        return self


class ImportValidationIssue(BaseModel):
    row_number: int | None = None
    code: str
    message: str


class ValidatedSystemRecord(BaseModel):
    """Minimal, canonical record suitable for a later explicit evidence step."""

    subject_id: str
    source_record_version: str
    source_as_of_date: datetime.date | None = None
    values: dict[str, Any]
    fingerprint_sha256: str

    def evidence_payload(self, contract: SystemRecordImportContract) -> dict[str, Any]:
        """Return the deterministic payload for a separately audited evidence ingest."""

        return {
            "source_system": contract.source_system,
            "mapping_id": contract.mapping_id,
            "subject_id": self.subject_id,
            "source_record_version": self.source_record_version,
            "source_as_of_date": (
                self.source_as_of_date.isoformat() if self.source_as_of_date else None
            ),
            "fields": self.values,
        }


class SystemRecordImportPreview(BaseModel):
    """A safe-to-log summary; validated record values are excluded by default."""

    contract_sha256: str
    source_sha256: str
    source_system: str
    mapping_id: str
    row_count: int
    accepted_record_count: int
    rejected_row_count: int
    ignored_columns: list[str]
    issues: list[ImportValidationIssue]
    records: list[ValidatedSystemRecord] = Field(default_factory=list, exclude=True)

    @property
    def is_valid(self) -> bool:
        return not self.issues

    def require_valid_records(self) -> list[ValidatedSystemRecord]:
        """Block partial imports. The caller must correct every reported issue first."""

        if not self.is_valid:
            raise SystemRecordImportError(
                "System-record import contains validation issues and cannot be materialised."
            )
        return self.records


class ImportReconciliationReport(BaseModel):
    previous_source_sha256: str
    candidate_source_sha256: str
    unchanged_record_count: int
    added_record_count: int
    changed_record_count: int
    removed_record_count: int
    requires_human_approval: bool
    changed_subject_ids: list[str] = Field(default_factory=list, exclude=True)
    removed_subject_ids: list[str] = Field(default_factory=list, exclude=True)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(value: bytes | Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical_json(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _parse_value(value: str, value_type: RecordValueType) -> Any:
    if value_type == "text":
        return value
    if value_type == "integer":
        if not re.fullmatch(r"[+-]?\d+", value):
            raise ValueError("must be an integer")
        return int(value)
    if value_type == "number":
        try:
            parsed = float(Decimal(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("must be a number") from exc
        if not math.isfinite(parsed):
            raise ValueError("must be a finite number")
        return parsed
    if value_type == "boolean":
        boolean_value = _BOOLEAN_VALUES.get(value.casefold())
        if boolean_value is None:
            raise ValueError("must be one of true, false, yes, no, 1, or 0")
        return boolean_value
    try:
        return datetime.date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("must be an ISO-8601 date") from exc


def _required_cell(row: dict[str | None, str | None], column: str) -> str:
    value = row.get(column)
    if value is None or not value.strip():
        raise ValueError(f"'{column}' is required")
    return value.strip()


def _record_fingerprint(
    subject_id: str,
    source_record_version: str,
    source_as_of_date: datetime.date | None,
    values: dict[str, Any],
) -> str:
    return _sha256(
        {
            "subject_id": subject_id,
            "source_record_version": source_record_version,
            "source_as_of_date": source_as_of_date.isoformat() if source_as_of_date else None,
            "values": values,
        }
    )


def preview_system_record_csv(
    content: bytes, contract: SystemRecordImportContract
) -> SystemRecordImportPreview:
    """Parse and validate a CSV export without persisting its contents or calling a vendor."""

    source_sha256 = _sha256(content)
    contract_sha256 = _sha256(contract.model_dump(mode="json"))
    if len(content) > contract.max_bytes:
        return SystemRecordImportPreview(
            contract_sha256=contract_sha256,
            source_sha256=source_sha256,
            source_system=contract.source_system,
            mapping_id=contract.mapping_id,
            row_count=0,
            accepted_record_count=0,
            rejected_row_count=0,
            ignored_columns=[],
            issues=[ImportValidationIssue(code="FILE_TOO_LARGE", message="CSV exceeds the approved import size.")],
        )
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return SystemRecordImportPreview(
            contract_sha256=contract_sha256,
            source_sha256=source_sha256,
            source_system=contract.source_system,
            mapping_id=contract.mapping_id,
            row_count=0,
            accepted_record_count=0,
            rejected_row_count=0,
            ignored_columns=[],
            issues=[ImportValidationIssue(code="INVALID_ENCODING", message="CSV must be UTF-8 encoded.")],
        )

    reader = csv.DictReader(io.StringIO(text), strict=True)
    headers = reader.fieldnames or []
    normalized_headers = [header.strip() for header in headers if header is not None]
    required_columns = {
        contract.subject_identifier_column,
        contract.source_record_version_column,
        *(field.source_column for field in contract.fields),
    }
    if contract.source_as_of_date_column:
        required_columns.add(contract.source_as_of_date_column)
    header_issues: list[ImportValidationIssue] = []
    if not headers:
        header_issues.append(ImportValidationIssue(code="MISSING_HEADER", message="CSV must contain a header row."))
    elif len(normalized_headers) != len(headers) or len(set(normalized_headers)) != len(normalized_headers):
        header_issues.append(ImportValidationIssue(code="INVALID_HEADER", message="CSV headers must be non-empty and unique."))
    else:
        missing_columns = sorted(required_columns.difference(normalized_headers))
        if missing_columns:
            header_issues.append(
                ImportValidationIssue(
                    code="MISSING_COLUMNS",
                    message=f"CSV is missing required columns: {', '.join(missing_columns)}.",
                )
            )
    ignored_columns = sorted(set(normalized_headers).difference(required_columns))
    if header_issues:
        return SystemRecordImportPreview(
            contract_sha256=contract_sha256,
            source_sha256=source_sha256,
            source_system=contract.source_system,
            mapping_id=contract.mapping_id,
            row_count=0,
            accepted_record_count=0,
            rejected_row_count=0,
            ignored_columns=ignored_columns,
            issues=header_issues,
        )

    issues: list[ImportValidationIssue] = []
    records: list[ValidatedSystemRecord] = []
    seen_subject_ids: set[str] = set()
    row_count = 0
    try:
        for row_number, raw_row in enumerate(reader, start=2):
            row_count += 1
            if row_count > contract.max_rows:
                issues.append(
                    ImportValidationIssue(
                        row_number=row_number,
                        code="ROW_LIMIT_EXCEEDED",
                        message="CSV exceeds the approved row limit.",
                    )
                )
                break
            row = {key.strip() if key else None: value for key, value in raw_row.items()}
            try:
                subject_id = _required_cell(row, contract.subject_identifier_column)
                if subject_id in seen_subject_ids:
                    raise ValueError("subject identifier is repeated")
                seen_subject_ids.add(subject_id)
                source_record_version = _required_cell(row, contract.source_record_version_column)
                source_as_of_date: datetime.date | None = None
                if contract.source_as_of_date_column:
                    source_as_of_date = datetime.date.fromisoformat(
                        _required_cell(row, contract.source_as_of_date_column)
                    )
                values: dict[str, Any] = {}
                for field in contract.fields:
                    raw_value = row.get(field.source_column)
                    if raw_value is None or not raw_value.strip():
                        if field.required:
                            raise ValueError(f"'{field.source_column}' is required")
                        continue
                    values[field.target_path] = _parse_value(raw_value.strip(), field.value_type)
                records.append(
                    ValidatedSystemRecord(
                        subject_id=subject_id,
                        source_record_version=source_record_version,
                        source_as_of_date=source_as_of_date,
                        values=values,
                        fingerprint_sha256=_record_fingerprint(
                            subject_id, source_record_version, source_as_of_date, values
                        ),
                    )
                )
            except ValueError as exc:
                issues.append(
                    ImportValidationIssue(row_number=row_number, code="INVALID_ROW", message=str(exc))
                )
    except csv.Error as exc:
        issues.append(ImportValidationIssue(code="MALFORMED_CSV", message=str(exc)))

    # A preview is useful for correction, but never a partial import source.
    # Discard every parsed record if any row or CSV-level validation failed.
    complete_records = records if not issues else []
    return SystemRecordImportPreview(
        contract_sha256=contract_sha256,
        source_sha256=source_sha256,
        source_system=contract.source_system,
        mapping_id=contract.mapping_id,
        row_count=row_count,
        accepted_record_count=len(complete_records),
        rejected_row_count=len(issues),
        ignored_columns=ignored_columns,
        issues=issues,
        records=complete_records,
    )


def reconcile_system_record_previews(
    previous: SystemRecordImportPreview, candidate: SystemRecordImportPreview
) -> ImportReconciliationReport:
    """Compare two fully valid previews without exposing record contents in output."""

    previous_records = {
        record.subject_id: record for record in previous.require_valid_records()
    }
    candidate_records = {
        record.subject_id: record for record in candidate.require_valid_records()
    }
    previous_subject_ids = set(previous_records)
    candidate_subject_ids = set(candidate_records)
    added_subject_ids = candidate_subject_ids.difference(previous_subject_ids)
    removed_subject_ids = previous_subject_ids.difference(candidate_subject_ids)
    shared_subject_ids = previous_subject_ids.intersection(candidate_subject_ids)
    changed_subject_ids = {
        subject_id
        for subject_id in shared_subject_ids
        if previous_records[subject_id].fingerprint_sha256
        != candidate_records[subject_id].fingerprint_sha256
    }
    return ImportReconciliationReport(
        previous_source_sha256=previous.source_sha256,
        candidate_source_sha256=candidate.source_sha256,
        unchanged_record_count=len(shared_subject_ids) - len(changed_subject_ids),
        added_record_count=len(added_subject_ids),
        changed_record_count=len(changed_subject_ids),
        removed_record_count=len(removed_subject_ids),
        requires_human_approval=bool(added_subject_ids or changed_subject_ids or removed_subject_ids),
        changed_subject_ids=sorted(changed_subject_ids),
        removed_subject_ids=sorted(removed_subject_ids),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a system-of-record CSV export.")
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    contract = SystemRecordImportContract.model_validate(
        json.loads(args.contract.read_text(encoding="utf-8"))
    )
    preview = preview_system_record_csv(args.csv.read_bytes(), contract)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(preview.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0 if preview.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
