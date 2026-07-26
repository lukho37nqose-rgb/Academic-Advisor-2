from contextlib import asynccontextmanager
import json
import re
import time

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from typing import Dict, Any, List, Optional, Literal, cast
import os
import uuid
import hashlib
import tempfile
from datetime import date, datetime, timedelta, timezone

from app.services.auth import (
    ensure_domain_access,
    ensure_subject_access,
    get_current_user,
    UserIdentity,
    Role,
    require_role,
)
from app.infrastructure.database import get_db_session, init_db, validate_production_database_safety
from app.infrastructure.repositories import (
    BackgroundJobConflictError,
    BackgroundJobRepository,
    DraftRepository,
    DecisionReviewConflictError,
    DecisionReviewRepository,
    DecisionReviewUnavailableError,
    DraftReleaseConflictError,
    EvidenceRepository,
    HandbookRepository,
    HandbookUploadConflictError,
    InstitutionalInputConflictError,
    InstitutionalInputRepository,
    GovernancePublicationBusyError,
    MetadataGovernanceRepository,
    PublicAccessRepository,
    PublicPolicyUnavailableError,
    QuickEditConflictError,
    PolicyAmbiguityConflictError,
    PolicyAmbiguityRepository,
    ReleaseApplicabilityConflictError,
    ReleaseVersionConflictError,
    ReasoningRepository,
    ReleaseRepository,
    ShadowCalibrationConflictError,
    ShadowCalibrationRepository,
    SystemRecordImportMappingConflictError,
    SystemRecordImportMappingRepository,
    acquire_domain_governance_lock,
)
from app.core.engine import generate_reasoning_graph
from app.core.models import RuleGraph, ReasoningGraph, EvaluationContext, Evidence, Fact, EvaluationSummary, Release
from app.core.compiler import compile_release_to_graph
from app.core.operators import UnsupportedOperatorError
from app.adapters.evidence import RawTextAdapter
from app.adapters.system_record_import import (
    SystemRecordImportContract,
    preview_system_record_csv,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.crypto import CryptoService
from app.infrastructure.idempotency import verify_idempotency_key, check_idempotency_cache, set_idempotency_cache, acquire_idempotency_lock, release_idempotency_lock
from app.infrastructure.blob_storage import BlobStorage
from app.core.extractor import EvidenceExtractor
from app.core.conflict import resolve_claims_to_facts
from app.core.explainer import format_explanation
from app.infrastructure.edge_registry import (
    DomainConfigurationError,
    EdgeRegistry,
    get_edge_registry,
)
from app.services.governance import get_role_permission_matrix
from app.services.ui_capabilities import get_interface_capabilities
from app.services.release_integrity import (
    ReleaseIntegrityError,
    require_release_integrity_for_evaluation,
    verify_release_bundle,
)
from app.services.institutional_intake import (
    InstitutionalInputError,
    InstitutionalIntakeRequest,
    build_institutional_input,
)
from app.services.access_controls import (
    enforce_public_support_rate_limit,
)
from app.services.shadow_calibration import (
    ShadowCalibrationCertificationRequest,
    ShadowCalibrationFindingResolutionRequest,
    ShadowCalibrationRunRequest,
    ShadowCalibrationSuiteInput,
    build_rehearsal_suite,
    validate_cases_against_domain_fields,
)
from app.sdk.pilot_rehearsal import run_pilot_rehearsal
from app.services.ocr_provider import is_configured as ocr_provider_is_configured
from app.infrastructure.telemetry import Telemetry, reset_request_id, set_request_id
from app.services.production_readiness import validate_production_readiness
from app.services.http_safety import allowed_hosts, apply_security_headers, cors_origins
from app.services.tenant_context import (
    begin_request_scope,
    public_support_request_scope,
    reset_request_scope,
)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_production_readiness()
    await init_db()
    await validate_production_database_safety()
    yield


app = FastAPI(title="Institutional Reasoning Engine API", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts()))
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(cors_origins()),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def system_record_import_max_bytes() -> int:
    """Bound an in-memory CSV preview independently of caller-provided limits."""

    configured = os.environ.get("SYSTEM_RECORD_IMPORT_MAX_BYTES", "20000000")
    try:
        value = int(configured)
    except ValueError:
        return 20_000_000
    return min(max(value, 1_024), 200_000_000)


async def validated_system_record_import_contract(
    *,
    raw_contract: dict[str, Any],
    tenant_id: str,
    domain_id: str,
    db: AsyncSession,
) -> SystemRecordImportContract:
    """Validate a no-code mapping against the selected domain's declared facts."""

    maximum_bytes = system_record_import_max_bytes()
    try:
        contract = SystemRecordImportContract.model_validate(raw_contract).model_copy(
            update={"max_bytes": min(int(raw_contract.get("max_bytes", maximum_bytes)), maximum_bytes)}
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail="The import mapping is invalid.") from exc

    approved_fields = await InstitutionalInputRepository(db).list_domain_fact_fields(
        tenant_id=tenant_id,
        domain_id=domain_id,
    )
    if approved_fields is None:
        raise HTTPException(status_code=404, detail="Decision domain was not found.")
    approved_targets = {field["target_path"] for field in approved_fields}
    unsupported_targets = sorted(
        field.target_path for field in contract.fields if field.target_path not in approved_targets
    )
    if unsupported_targets:
        raise HTTPException(
            status_code=422,
            detail="The mapping contains facts that are not declared for this decision domain.",
        )
    return contract


@app.middleware("http")
async def request_observability(request: Request, call_next):
    """Attach a safe correlation ID without logging request bodies or queries."""
    scope_tokens = begin_request_scope(public=request.url.path.startswith("/api/v1/public/"))
    supplied_id = request.headers.get("X-Request-ID", "")
    request_id = supplied_id if _REQUEST_ID_PATTERN.fullmatch(supplied_id) else uuid.uuid4().hex
    request.state.request_id = request_id
    context_token = set_request_id(request_id)
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        Telemetry.log_error(
            exc,
            {"method": request.method, "path": request.url.path, "stage": "request"},
        )
        raise
    else:
        duration_ms = round((time.perf_counter() - started_at) * 1000)
        Telemetry.log_event(
            "http_request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        apply_security_headers(response)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        reset_request_id(context_token)
        reset_request_scope(scope_tokens)


@app.get("/health/live", include_in_schema=False)
async def health_live() -> dict[str, str]:
    """Process liveness probe; it must not depend on external infrastructure."""
    return {"status": "ok", "service": "institutional-reasoning-engine"}


@app.get("/health/ready", include_in_schema=False)
async def health_ready(db: AsyncSession = Depends(get_db_session)) -> dict[str, str]:
    """Readiness probe confirms that the configured database can accept a query."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Service dependencies are not ready.") from exc
    return {"status": "ready", "service": "institutional-reasoning-engine"}

# --- DTOs ---

class EvidenceIngestionRequest(BaseModel):
    domain_id: str = Field(min_length=1)
    subject_id: str
    content: str
    
class EvaluateRequest(BaseModel):
    rule_graph_id: str
    evidence_id: str
    subject_id: str
    domain_id: str
    release_version: str
    as_of_date: Optional[date] = None
    applicability_context: Dict[str, str] = Field(default_factory=dict)

    @field_validator("applicability_context")
    @classmethod
    def validate_applicability_context(cls, value: Dict[str, str]) -> Dict[str, str]:
        if len(value) > 20:
            raise ValueError("At most 20 policy applicability selectors may be supplied.")
        cleaned: Dict[str, str] = {}
        for key, item in value.items():
            normalized_key = key.strip()
            normalized_value = item.strip()
            if not normalized_key or not normalized_value:
                raise ValueError("Policy applicability selectors cannot be blank.")
            if len(normalized_key) > 80 or len(normalized_value) > 200:
                raise ValueError("Policy applicability selectors are too long.")
            cleaned[normalized_key] = normalized_value
        return cleaned

class DraftPolicyRequest(BaseModel):
    domain_id: str
    policy_name: str
    payload: dict

class ReleaseApplicabilityCriterion(BaseModel):
    """A plain-language policy selector, configured without JSON or code."""

    attribute: str = Field(min_length=1, max_length=80)
    values: list[str] = Field(min_length=1, max_length=50)

    @field_validator("attribute")
    @classmethod
    def trim_attribute(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Applicability attribute cannot be blank.")
        return trimmed

    @field_validator("values")
    @classmethod
    def trim_values(cls, values: list[str]) -> list[str]:
        trimmed = [value.strip() for value in values]
        if any(not value for value in trimmed):
            raise ValueError("Applicability values cannot be blank.")
        if any(len(value) > 200 for value in trimmed):
            raise ValueError("Applicability values are too long.")
        if len(set(trimmed)) != len(trimmed):
            raise ValueError("Applicability values must be unique.")
        return trimmed


class ReleasePolicyRequest(BaseModel):
    draft_id: str
    version: str = Field(min_length=1, max_length=80)
    effective_from: date
    effective_until: Optional[date] = None
    applicability: list[ReleaseApplicabilityCriterion] = Field(default_factory=list, max_length=10)

    @field_validator("version")
    @classmethod
    def trim_release_version(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Release version cannot be blank.")
        return trimmed

    @model_validator(mode="after")
    def validate_effectivity_and_selectors(self) -> "ReleasePolicyRequest":
        if self.effective_until and self.effective_until < self.effective_from:
            raise ValueError("Effective end date must be on or after the effective start date.")
        attributes = [criterion.attribute for criterion in self.applicability]
        if len(set(attributes)) != len(attributes):
            raise ValueError("Each applicability attribute may be supplied only once.")
        return self


class PolicyAmbiguityRequest(BaseModel):
    domain_id: str = Field(min_length=1)
    source_citation: str = Field(min_length=3, max_length=2000)
    question: str = Field(min_length=10, max_length=4000)
    interpretation_options: list[str] = Field(min_length=2, max_length=10)

    @field_validator("domain_id", "source_citation", "question")
    @classmethod
    def trim_ambiguity_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Ambiguity values cannot be blank.")
        return trimmed

    @field_validator("interpretation_options")
    @classmethod
    def validate_interpretation_options(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("Interpretation options cannot be blank.")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Interpretation options must be distinct.")
        return cleaned


class PolicyAmbiguityResolutionRequest(BaseModel):
    domain_id: str = Field(min_length=1)
    resolution: str = Field(min_length=10, max_length=4000)
    source_reference: str = Field(min_length=3, max_length=2000)

    @field_validator("domain_id", "resolution", "source_reference")
    @classmethod
    def trim_resolution_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Resolution values cannot be blank.")
        return trimmed

class QuickEditRequest(BaseModel):
    domain_id: str = Field(min_length=1)
    target_type: str = Field(min_length=1)
    target_id: str = Field(min_length=1, description="Stable Edge resource identifier.")
    field: str = Field(min_length=1)
    old_value: Optional[str] = None
    new_value: str = Field(min_length=1)
    reason: str = Field(min_length=5)
    source_reference: Optional[str] = None

    @field_validator("target_type", "target_id", "field", "new_value", "reason", "domain_id")
    @classmethod
    def trim_required_strings(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Value cannot be blank.")
        return trimmed


class SystemRecordImportMappingRequest(BaseModel):
    """A staff-authored configuration, not an uploaded record export."""

    domain_id: str = Field(min_length=1)
    contract: dict[str, Any]

    @field_validator("domain_id")
    @classmethod
    def trim_domain_id(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Domain identifier cannot be blank.")
        return trimmed


class SystemRecordImportMappingApprovalRequest(BaseModel):
    domain_id: str = Field(min_length=1)
    note: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("domain_id")
    @classmethod
    def trim_domain_id(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Domain identifier cannot be blank.")
        return trimmed

    @field_validator("note")
    @classmethod
    def trim_note(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value and value.strip() else None


class SystemRecordImportMappingRejectionRequest(BaseModel):
    domain_id: str = Field(min_length=1)
    reason: str = Field(min_length=3, max_length=2000)

    @field_validator("domain_id", "reason")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("A rejection reason is required.")
        return trimmed


class PublicSupportRequest(BaseModel):
    category: Literal["missing_information", "unique_circumstance", "accessibility", "other"]
    contact_details: Optional[str] = Field(default=None, max_length=320)
    message: str = Field(min_length=10, max_length=2000)

    @field_validator("message")
    @classmethod
    def trim_support_message(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Message cannot be blank.")
        return trimmed


class SupportRequestStatusUpdate(BaseModel):
    """Human workflow state only; this cannot alter a policy or decision."""

    domain_id: str = Field(min_length=1)
    status: Literal["OPEN", "IN_PROGRESS", "CLOSED"]

    @field_validator("domain_id")
    @classmethod
    def trim_domain_id(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Domain identifier cannot be blank.")
        return trimmed


class DecisionReviewSubmission(BaseModel):
    """A subject's request to review their own immutable decision trace."""

    domain_id: str = Field(min_length=1)
    reasoning_graph_id: str = Field(min_length=1)
    category: Literal[
        "evidence_correction",
        "missing_evidence",
        "policy_interpretation",
        "exceptional_circumstance",
        "explanation_accessibility",
    ]
    message: str = Field(min_length=10, max_length=4000)
    disputed_fact_paths: list[str] = Field(default_factory=list, max_length=25)
    submitted_evidence_ids: list[str] = Field(default_factory=list, max_length=25)

    @field_validator("domain_id", "reasoning_graph_id", "message")
    @classmethod
    def trim_review_strings(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Review values cannot be blank.")
        return trimmed

    @field_validator("disputed_fact_paths", "submitted_evidence_ids")
    @classmethod
    def trim_review_identifiers(cls, values: list[str]) -> list[str]:
        trimmed = [value.strip() for value in values]
        if any(not value for value in trimmed):
            raise ValueError("Review identifiers cannot be blank.")
        if len(set(trimmed)) != len(trimmed):
            raise ValueError("Review identifiers must not be repeated.")
        return trimmed


class DecisionReviewCaseUpdate(BaseModel):
    domain_id: str = Field(min_length=1)
    status: Literal["ACKNOWLEDGED", "UNDER_REVIEW", "RESOLVED", "CLOSED"]
    resolution: Optional[Literal[
        "DECISION_CONFIRMED",
        "RE_EVALUATION_REQUIRED",
        "POLICY_CLARIFICATION_PROVIDED",
        "EXCEPTION_REFERRED",
        "OUT_OF_SCOPE",
    ]] = None
    response_message: Optional[str] = Field(default=None, max_length=4000)

    @field_validator("domain_id")
    @classmethod
    def trim_review_domain(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Domain identifier cannot be blank.")
        return trimmed

    @field_validator("response_message")
    @classmethod
    def trim_review_response(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value else value


def ensure_decision_review_case_access(user: UserIdentity, review_case: dict[str, Any]) -> None:
    """Subjects see only their own cases; staff remain constrained to domains."""
    if user.role == Role.SUBJECT:
        ensure_subject_access(user, cast(str, review_case["subject_id"]))
    else:
        ensure_domain_access(user, cast(str, review_case["domain_id"]))


class HandbookUploadSessionRequest(BaseModel):
    domain_id: str = Field(min_length=1)
    file_name: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=128)
    file_size_bytes: int = Field(gt=0)

    @field_validator("domain_id", "file_name", "content_type")
    @classmethod
    def trim_source_values(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Handbook upload values cannot be blank.")
        return trimmed


class OCRReviewDecisionRequest(BaseModel):
    action: Literal["ACCEPT", "CORRECT", "REJECT"]
    reviewed_text: Optional[str] = Field(default=None, max_length=100_000)

    @field_validator("reviewed_text")
    @classmethod
    def trim_optional_review_text(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value else value


def handbook_upload_max_bytes() -> int:
    raw_value = os.environ.get("HANDBOOK_UPLOAD_MAX_BYTES", str(250 * 1024 * 1024))
    try:
        maximum = int(raw_value)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="HANDBOOK_UPLOAD_MAX_BYTES must be a whole number.") from exc
    if maximum < 1024 * 1024:
        raise HTTPException(status_code=500, detail="HANDBOOK_UPLOAD_MAX_BYTES must be at least 1 MB.")
    return maximum


def handbook_direct_upload_max_bytes() -> int:
    raw_value = os.environ.get("HANDBOOK_DIRECT_UPLOAD_MAX_BYTES", str(2 * 1024 * 1024 * 1024))
    try:
        maximum = int(raw_value)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="HANDBOOK_DIRECT_UPLOAD_MAX_BYTES must be a whole number.") from exc
    if maximum < handbook_upload_max_bytes():
        raise HTTPException(status_code=500, detail="HANDBOOK_DIRECT_UPLOAD_MAX_BYTES must be at least HANDBOOK_UPLOAD_MAX_BYTES.")
    return maximum


def handbook_upload_session_ttl_seconds() -> int:
    raw_value = os.environ.get("HANDBOOK_UPLOAD_SESSION_TTL_SECONDS", "900")
    try:
        ttl = int(raw_value)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="HANDBOOK_UPLOAD_SESSION_TTL_SECONDS must be a whole number.") from exc
    if ttl < 60 or ttl > 3600:
        raise HTTPException(status_code=500, detail="HANDBOOK_UPLOAD_SESSION_TTL_SECONDS must be between 60 and 3600 seconds.")
    return ttl


def handbook_source_metadata(file_name: str, content_type: str) -> tuple[str, str]:
    normalized_name = os.path.basename(file_name or "handbook.pdf")
    if not normalized_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Handbook uploads must be PDF files.")
    normalized_type = content_type or "application/pdf"
    if normalized_type not in {"application/pdf", "application/x-pdf"}:
        raise HTTPException(status_code=422, detail="Handbook uploads must have a PDF content type.")
    return normalized_name, normalized_type

# --- Endpoints ---


@app.get("/api/v1/session/capabilities")
async def get_session_capabilities(
    user: UserIdentity = Depends(get_current_user),
):
    """Return the authenticated account's approved reference-client workspace."""
    return get_interface_capabilities(user)

@app.post("/api/v1/evidence", status_code=201)
async def ingest_evidence(
    request: EvidenceIngestionRequest,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.SUBJECT])),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Ingests unstructured evidence text, hashes it, stores it via BlobStorage, 
    and returns a canonical Evidence ID.
    """
    ensure_domain_access(user, request.domain_id)
    ensure_subject_access(user, request.subject_id)
    adapter = RawTextAdapter()
    try:
        evidence = await adapter.ingest(
            tenant_id=user.tenant_id,
            subject_id=request.subject_id,
            raw_payload=request.content,
        )
        
        evidence_repo = EvidenceRepository(db)
        await evidence_repo.create_evidence(
            evidence,
            tenant_id=user.tenant_id,
            domain_id=request.domain_id,
        )
        return {**evidence.model_dump(), "domain_id": request.domain_id}
    except HTTPException:
        raise
    except Exception as exc:
        Telemetry.log_error(exc, {"stage": "evidence_ingestion"})
        raise HTTPException(
            status_code=503,
            detail="Evidence ingestion is temporarily unavailable.",
        ) from exc

@app.post("/api/v1/evaluate", status_code=202)
async def start_evaluation(
    request: EvaluateRequest,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.SUBJECT])),
    db: AsyncSession = Depends(get_db_session),
    idemp_key: str = Depends(verify_idempotency_key)
):
    """
    Kicks off an evaluation of evidence against a specific rule graph.
    Protected by atomic SET NX idempotency lock.
    """
    # 1. Check for cached response
    cached_response = await check_idempotency_cache(idemp_key)
    if cached_response:
        return cached_response
        
    # 2. Acquire atomic SET NX lock
    lock_acquired = await acquire_idempotency_lock(idemp_key)
    if not lock_acquired:
         raise HTTPException(status_code=409, detail="A request with this Idempotency-Key is already processing.")
         
    try:
        repo = ReleaseRepository(db)
        reasoning_repo = ReasoningRepository(db)
        evidence_repo = EvidenceRepository(db)

        ensure_domain_access(user, request.domain_id)
        ensure_subject_access(user, request.subject_id)

        release = await repo.get_release(request.domain_id, request.release_version)
        if not release:
            raise HTTPException(
                status_code=404,
                detail=f"Release {request.release_version} was not found for domain {request.domain_id}.",
            )
        if release.rule_graph_id != request.rule_graph_id:
            raise HTTPException(
                status_code=409,
                detail="The supplied rule graph does not belong to the requested immutable release.",
            )

        rule_graph = await repo.get_compiled_rule_graph(request.rule_graph_id)
        if not rule_graph:
            raise HTTPException(status_code=424, detail=f"Compiled rule graph {request.rule_graph_id} not found.")
        if rule_graph.release_id != release.id:
            raise HTTPException(status_code=409, detail="Compiled rule graph release binding is invalid.")
        try:
            require_release_integrity_for_evaluation(release, rule_graph)
        except ReleaseIntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="The selected release failed integrity verification and cannot be evaluated.",
            ) from exc

        if release.effective_from is not None:
            if request.as_of_date is None:
                raise HTTPException(
                    status_code=422,
                    detail="An as_of_date is required to evaluate a release with an effective period.",
                )
            if request.as_of_date < release.effective_from or (
                release.effective_until is not None and request.as_of_date > release.effective_until
            ):
                raise HTTPException(
                    status_code=409,
                    detail="The selected release was not effective on the supplied as_of_date.",
                )

        missing_selectors = [key for key in release.applicability if key not in request.applicability_context]
        if missing_selectors:
            raise HTTPException(
                status_code=422,
                detail=(
                    "The selected release requires policy applicability selectors: "
                    + ", ".join(sorted(missing_selectors))
                    + "."
                ),
            )
        mismatched_selectors = [
            key
            for key, allowed_values in release.applicability.items()
            if request.applicability_context.get(key) not in allowed_values
        ]
        if mismatched_selectors:
            raise HTTPException(
                status_code=409,
                detail=(
                    "The selected release does not apply to the supplied policy context: "
                    + ", ".join(sorted(mismatched_selectors))
                    + "."
                ),
            )
        
        # Initialize Context
        context = EvaluationContext(
            tenant_id=user.tenant_id,
            subject_id=request.subject_id,
            domain_id=request.domain_id,
            release_version=request.release_version,
            policy_as_of_date=request.as_of_date,
            policy_context=request.applicability_context,
        )
        
        # Verify and fetch real evidence from database
        stored_evidence = await evidence_repo.get_evidence(
            request.evidence_id,
            tenant_id=user.tenant_id,
        )
        if not stored_evidence:
             raise HTTPException(status_code=404, detail="Evidence not found or missing storage key.")
        if stored_evidence.domain_id != request.domain_id:
            raise HTTPException(
                status_code=409,
                detail="Evidence belongs to a different domain than the requested evaluation.",
            )
        if stored_evidence.evidence.subject_id != request.subject_id:
            raise HTTPException(
                status_code=409,
                detail="Evidence belongs to a different subject than the requested evaluation.",
            )
        ensure_subject_access(user, stored_evidence.evidence.subject_id)
             
        # Fetch the stream representing the evidence.
        evidence = stored_evidence.evidence
        if not evidence.storage_key:
            raise HTTPException(status_code=404, detail="Evidence not found or missing storage key.")
        stream = BlobStorage.get_stream(evidence.storage_key)

        # Extract Claims
        extractor = EvidenceExtractor(evidence_id=evidence.id)
        claims = await extractor.extract_claims_from_stream(stream)

        # Resolve Facts
        facts = resolve_claims_to_facts(claims)
        
        # Execute Engine
        reasoning_graph = generate_reasoning_graph(context, rule_graph, facts)
        
        # Extract Decision
        final_node = next((n for n in reasoning_graph.nodes.values() if n.type == "conclusion"), None)
        if final_node is None:
            raise HTTPException(status_code=500, detail="Evaluation did not produce a complete reasoning trace.")
        passed = final_node.data.get("overall_passed")
        if passed is not True and passed is not False and passed != "NEEDS_MANUAL_REVIEW":
            raise HTTPException(status_code=500, detail="Evaluation produced an unsupported trace outcome.")
        confidence = final_node.computed_confidence
        
        if passed == "NEEDS_MANUAL_REVIEW":
            decision = "NEEDS_MANUAL_REVIEW"
        elif passed:
            decision = "ELIGIBLE"
        else:
            decision = "INELIGIBLE"

        # Generate the human-readable explanation strictly after deterministic
        # evaluation. It only reads the trace and cannot change the outcome.
        reasoning_graph.explanation = await format_explanation(reasoning_graph)

        # Persist Trace (now including the explanation, in the same JSON blob)
        await reasoning_repo.save_evaluation_artifacts(
            graph=reasoning_graph,
            overall_decision=decision,
            overall_confidence=confidence,
            tenant_id=user.tenant_id,
            domain_id=request.domain_id,
            release_id=release.id,
            evidence_id=evidence.id,
            claims=claims,
            facts=facts,
        )
        
        summary = EvaluationSummary(
            decision=decision,  # type: ignore
            overall_confidence=confidence,
            reasoning_graph_id=reasoning_graph.id,
            release_version=context.release_version
        )
        
        response_data = summary.model_dump()
        
        # Save final response to idempotency cache
        await set_idempotency_cache(idemp_key, response_data)
        
        return response_data
    finally:
        # Release the lock so future retries hit the cache check rather than conflict
        await release_idempotency_lock(idemp_key)

@app.get("/api/v1/reasoning/{graph_id}")
async def get_reasoning_graph(
    graph_id: str,
    user: UserIdentity = Depends(require_role([
        Role.SUBJECT,
        Role.TENANT_ADMIN,
        Role.ASSISTANCE_COORDINATOR,
        Role.AUDITOR,
    ])),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Retrieves the reasoning graph (audit trail) for a given evaluation.
    """
    repo = ReasoningRepository(db)
    
    # We will need to adjust the actual repository method call based on what exists
    payload = await repo.get_reasoning_graph(graph_id, tenant_id=user.tenant_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Reasoning graph not found")
    if not payload.evaluation_context:
        raise HTTPException(status_code=409, detail="Reasoning graph lacks replayable evaluation context.")
    ensure_domain_access(user, payload.evaluation_context.domain_id)
    ensure_subject_access(user, payload.subject_id)
        
    return payload


@app.post("/api/v1/governance/drafts", status_code=201)
async def create_draft_policy(
    request: DraftPolicyRequest,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.RULE_AUTHOR])),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Saves a new draft policy for review. The draft is scoped to the
    authenticated user's tenant and author -- a draft cannot be created on
    another tenant's behalf, and the author is recorded from the JWT, not
    from the request body, so it can't be spoofed at approval time.

    The submitted payload is compiled before it is persisted. This catches
    invalid operators, missing roots, and malformed leaf nodes while the
    author is still editing, instead of leaving the reviewer to discover a
    broken draft at release time.
    """
    ensure_domain_access(user, request.domain_id)
    try:
        compile_release_to_graph("draft_validation_" + uuid.uuid4().hex, request.payload)
    except (ValueError, UnsupportedOperatorError) as e:
        raise HTTPException(status_code=422, detail=f"Draft failed compilation: {str(e)}")

    draft_repo = DraftRepository(db)
    draft_id = "draft_" + uuid.uuid4().hex
    await draft_repo.create_draft(
        draft_id=draft_id,
        tenant_id=user.tenant_id,
        domain_id=request.domain_id,
        policy_name=request.policy_name,
        author_id=user.user_id,
        payload=request.payload
    )
    return {"draft_id": draft_id, "status": "PENDING"}


@app.post("/api/v1/admin/institutional-inputs/domains", status_code=201)
async def create_institutional_domain_input(
    request: InstitutionalIntakeRequest,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN])),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Turns guided institutional input into a tenant domain and pending policy
    draft. Administrators submit labels, fact types, rule choices, and source
    citations; the runtime creates the neutral schema and expression tree.
    """
    try:
        built_input = build_institutional_input(request)
        compile_release_to_graph("intake_validation_" + uuid.uuid4().hex, built_input.policy_payload)
    except (InstitutionalInputError, ValueError, UnsupportedOperatorError) as exc:
        raise HTTPException(status_code=422, detail=f"Institutional input is invalid: {exc}")

    domain_id = "dom_" + uuid.uuid4().hex
    draft_id = "draft_" + uuid.uuid4().hex
    requested_policy_name = request.policy_name.strip() if request.policy_name else ""
    policy_name = requested_policy_name or f"{request.domain_name.strip()} initial policy"
    repository = InstitutionalInputRepository(db)
    try:
        await repository.create_domain_with_draft(
            tenant_id=user.tenant_id,
            institution_name=request.institution_name.strip(),
            domain_id=domain_id,
            domain_name=request.domain_name.strip(),
            schema_definition=built_input.schema_definition,
            draft_id=draft_id,
            policy_name=policy_name,
            author_id=user.user_id,
            policy_payload=built_input.policy_payload,
        )
    except InstitutionalInputConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {
        "tenant_id": user.tenant_id,
        "domain_id": domain_id,
        "domain_name": request.domain_name.strip(),
        "draft_id": draft_id,
        "policy_name": policy_name,
        "status": "PENDING_REVIEW",
        "fact_count": built_input.fact_count,
        "rule_count": built_input.rule_count,
        "next_step": "A separate release approver must review and publish this policy draft.",
    }


@app.get("/api/v1/governance/drafts")
async def list_pending_policy_reviews(
    user: UserIdentity = Depends(require_role([
        Role.TENANT_ADMIN,
        Role.RULE_APPROVER,
        Role.AUDITOR,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    """Lists pending draft reviews without exposing raw policy implementation."""
    domain_ids = None if user.role == Role.TENANT_ADMIN else user.domain_ids
    return {
        "items": await DraftRepository(db).list_pending_reviews(
            tenant_id=user.tenant_id,
            domain_ids=domain_ids,
        )
    }


@app.get("/api/v1/governance/drafts/{draft_id}/review")
async def get_pending_policy_review(
    draft_id: str,
    user: UserIdentity = Depends(require_role([
        Role.TENANT_ADMIN,
        Role.RULE_APPROVER,
        Role.AUDITOR,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    """Shows an approver the policy's labels, values, and citations, not JSON."""
    review = await DraftRepository(db).get_pending_review(
        draft_id=draft_id,
        tenant_id=user.tenant_id,
    )
    if review is None:
        raise HTTPException(status_code=404, detail="Pending draft review was not found.")
    ensure_domain_access(user, review["domain_id"])
    return review


@app.get("/api/v1/admin/domains")
async def list_admin_domains(
    user: UserIdentity = Depends(require_role([
        Role.TENANT_ADMIN,
        Role.METADATA_STEWARD,
        Role.ASSISTANCE_COORDINATOR,
        Role.RULE_AUTHOR,
        Role.RULE_APPROVER,
        Role.POLICY_OWNER,
        Role.AUDITOR,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    """Lists domains a staff member may use to triage assistance requests."""
    domain_ids = None if user.role == Role.TENANT_ADMIN else user.domain_ids
    return {
        "items": await InstitutionalInputRepository(db).list_domains(
            tenant_id=user.tenant_id,
            domain_ids=domain_ids,
        )
    }


@app.get("/api/v1/admin/domains/{domain_id}/record-import-fields")
async def list_record_import_fields(
    domain_id: str,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.RULE_AUTHOR])),
    db: AsyncSession = Depends(get_db_session),
):
    """Returns only schema-approved, labelled destinations for a CSV mapping."""

    ensure_domain_access(user, domain_id)
    fields = await InstitutionalInputRepository(db).list_domain_fact_fields(
        tenant_id=user.tenant_id,
        domain_id=domain_id,
    )
    if fields is None:
        raise HTTPException(status_code=404, detail="Decision domain was not found.")
    return {"items": fields}


async def _verified_calibration_release(
    *,
    repository: ReleaseRepository,
    release_id: str,
    domain_id: str,
) -> tuple[Release, RuleGraph]:
    """Calibration only compares cases against a cryptographically verifiable release."""
    release = await repository.get_release_by_id(release_id)
    if release is None or release.domain_id != domain_id:
        raise HTTPException(status_code=404, detail="Approved policy release was not found for this domain.")
    compiled_rule_graph = await repository.get_compiled_rule_graph(release.rule_graph_id)
    if compiled_rule_graph is None:
        raise HTTPException(status_code=409, detail="The approved policy release has no compiled rule graph.")
    valid, reason = verify_release_bundle(release, compiled_rule_graph)
    if not valid:
        raise HTTPException(
            status_code=409,
            detail=f"This release cannot be used for shadow calibration: {reason}.",
        )
    return release, compiled_rule_graph


@app.get("/api/v1/governance/domains/{domain_id}/calibration-releases")
async def list_calibration_releases(
    domain_id: str,
    user: UserIdentity = Depends(require_role([
        Role.TENANT_ADMIN,
        Role.RULE_AUTHOR,
        Role.RULE_APPROVER,
        Role.POLICY_OWNER,
        Role.AUDITOR,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    """Lists releases and makes their calibration eligibility visible before selection."""
    ensure_domain_access(user, domain_id)
    repository = ReleaseRepository(db)
    items = []
    for release in await repository.list_domain_releases(domain_id):
        compiled_rule_graph = await repository.get_compiled_rule_graph(release.rule_graph_id)
        valid, reason = verify_release_bundle(release, compiled_rule_graph)
        items.append({
            "release_id": release.id,
            "version": release.version,
            "effective_from": release.effective_from.isoformat() if release.effective_from else None,
            "effective_until": release.effective_until.isoformat() if release.effective_until else None,
            "calibration_ready": valid,
            "calibration_blocker": None if valid else reason,
        })
    return {"items": items}


@app.post("/api/v1/governance/shadow-calibrations", status_code=201)
async def create_shadow_calibration(
    request: ShadowCalibrationSuiteInput,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.RULE_AUTHOR])),
    db: AsyncSession = Depends(get_db_session),
):
    """Submits immutable representative cases for independent shadow calibration."""
    ensure_domain_access(user, request.domain_id)
    fields = await InstitutionalInputRepository(db).list_domain_fact_fields(
        tenant_id=user.tenant_id,
        domain_id=request.domain_id,
    )
    if fields is None:
        raise HTTPException(status_code=404, detail="Decision domain was not found.")
    try:
        validate_cases_against_domain_fields(request.cases, fields)
        await _verified_calibration_release(
            repository=ReleaseRepository(db),
            release_id=request.release_id,
            domain_id=request.domain_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    suite_id = "calibration_suite_" + uuid.uuid4().hex
    cases = [
        {
            "id": "calibration_case_" + uuid.uuid4().hex,
            "case_reference": case.case_reference,
            "description": case.description,
            "recorded_decision": case.recorded_decision,
            "recorded_outcome_reference": case.recorded_outcome_reference,
            "facts": [fact.model_dump() for fact in case.facts],
        }
        for case in request.cases
    ]
    repository = ShadowCalibrationRepository(db)
    try:
        await repository.create_suite(
            suite_id=suite_id,
            tenant_id=user.tenant_id,
            domain_id=request.domain_id,
            release_id=request.release_id,
            name=request.name,
            description=request.description,
            data_basis=request.data_basis,
            privacy_approval_reference=request.privacy_approval_reference,
            policy_as_of_date=request.policy_as_of_date,
            author_id=user.user_id,
            cases=cases,
        )
    except ShadowCalibrationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    suite = await repository.get_suite(
        suite_id=suite_id,
        tenant_id=user.tenant_id,
        domain_id=request.domain_id,
    )
    if suite is None:
        raise HTTPException(status_code=409, detail="Calibration suite could not be loaded after submission.")
    return suite


@app.get("/api/v1/governance/shadow-calibrations")
async def list_shadow_calibrations(
    domain_id: str,
    user: UserIdentity = Depends(require_role([
        Role.TENANT_ADMIN,
        Role.RULE_AUTHOR,
        Role.RULE_APPROVER,
        Role.POLICY_OWNER,
        Role.AUDITOR,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    ensure_domain_access(user, domain_id)
    return {
        "items": await ShadowCalibrationRepository(db).list_suites(
            tenant_id=user.tenant_id,
            domain_id=domain_id,
        )
    }


@app.get("/api/v1/governance/shadow-calibrations/{suite_id}")
async def get_shadow_calibration(
    suite_id: str,
    domain_id: str,
    user: UserIdentity = Depends(require_role([
        Role.TENANT_ADMIN,
        Role.RULE_AUTHOR,
        Role.RULE_APPROVER,
        Role.POLICY_OWNER,
        Role.AUDITOR,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    ensure_domain_access(user, domain_id)
    suite = await ShadowCalibrationRepository(db).get_suite(
        suite_id=suite_id,
        tenant_id=user.tenant_id,
        domain_id=domain_id,
    )
    if suite is None:
        raise HTTPException(status_code=404, detail="Shadow calibration suite was not found.")
    return suite


@app.post("/api/v1/governance/shadow-calibrations/{suite_id}/certify")
async def certify_shadow_calibration(
    suite_id: str,
    request: ShadowCalibrationCertificationRequest,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.RULE_APPROVER, Role.POLICY_OWNER])),
    db: AsyncSession = Depends(get_db_session),
):
    """Requires an independent institutional role to certify the comparison inputs."""
    ensure_domain_access(user, request.domain_id)
    try:
        suite = await ShadowCalibrationRepository(db).certify_suite(
            suite_id=suite_id,
            tenant_id=user.tenant_id,
            domain_id=request.domain_id,
            actor_id=user.user_id,
            note=request.note,
        )
    except ShadowCalibrationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if suite is None:
        raise HTTPException(status_code=404, detail="Shadow calibration suite was not found.")
    return suite


@app.post("/api/v1/governance/shadow-calibrations/{suite_id}/run")
async def run_shadow_calibration(
    suite_id: str,
    request: ShadowCalibrationRunRequest,
    user: UserIdentity = Depends(require_role([
        Role.TENANT_ADMIN,
        Role.RULE_AUTHOR,
        Role.RULE_APPROVER,
        Role.POLICY_OWNER,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    """Runs a certified suite in memory and stores only a shadow comparison report."""
    ensure_domain_access(user, request.domain_id)
    repository = ShadowCalibrationRepository(db)
    suite = await repository.get_suite(
        suite_id=suite_id,
        tenant_id=user.tenant_id,
        domain_id=request.domain_id,
    )
    if suite is None:
        raise HTTPException(status_code=404, detail="Shadow calibration suite was not found.")
    try:
        release, _ = await _verified_calibration_release(
            repository=ReleaseRepository(db),
            release_id=cast(str, suite["release_id"]),
            domain_id=request.domain_id,
        )
        signed_policy = release.signed_payload.get("policy")
        if not isinstance(signed_policy, dict):
            raise ValueError("The verified release has no signed policy payload.")
        rehearsal_suite = build_rehearsal_suite(
            suite_id=cast(str, suite["suite_id"]),
            tenant_id=user.tenant_id,
            domain_id=request.domain_id,
            release_id=release.id,
            release_version=release.version,
            policy_as_of_date=date.fromisoformat(cast(str, suite["policy_as_of_date"])),
            description=cast(str, suite["description"]),
            cases=cast(list[dict[str, Any]], suite["cases"]),
            evaluation_timestamp=datetime.now(timezone.utc).isoformat(),
        )
        report = run_pilot_rehearsal(signed_policy, rehearsal_suite).model_dump(mode="json")
        run = await repository.record_run(
            suite_id=suite_id,
            tenant_id=user.tenant_id,
            domain_id=request.domain_id,
            actor_id=user.user_id,
            report=report,
        )
    except (ShadowCalibrationConflictError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "run": run,
        "message": "Shadow calibration completed. No institutional record or operative decision was changed.",
    }


@app.patch("/api/v1/governance/shadow-calibration-findings/{finding_id}")
async def resolve_shadow_calibration_finding(
    finding_id: str,
    request: ShadowCalibrationFindingResolutionRequest,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.POLICY_OWNER, Role.RULE_APPROVER])),
    db: AsyncSession = Depends(get_db_session),
):
    """Classifies a mismatch without changing its source case, release, or report."""
    ensure_domain_access(user, request.domain_id)
    try:
        finding = await ShadowCalibrationRepository(db).resolve_finding(
            finding_id=finding_id,
            tenant_id=user.tenant_id,
            domain_id=request.domain_id,
            actor_id=user.user_id,
            classification=request.classification,
            note=request.note,
        )
    except ShadowCalibrationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if finding is None:
        raise HTTPException(status_code=404, detail="Shadow calibration mismatch was not found.")
    return finding


@app.post("/api/v1/admin/system-record-imports/preview")
async def preview_system_record_import(
    domain_id: str = Form(...),
    contract_json: str = Form(...),
    file: UploadFile = File(...),
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.RULE_AUTHOR])),
    db: AsyncSession = Depends(get_db_session),
):
    """Validate a one-way CSV export without persisting it or calling its source."""

    ensure_domain_access(user, domain_id)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="A CSV export file is required.")
    maximum_bytes = system_record_import_max_bytes()
    content = await file.read(maximum_bytes + 1)
    if len(content) > maximum_bytes:
        raise HTTPException(status_code=413, detail="CSV exceeds the server preview size limit.")
    try:
        raw_contract = json.loads(contract_json)
        if not isinstance(raw_contract, dict):
            raise ValueError("Import contract must be an object.")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="The import mapping is invalid.") from exc
    contract = await validated_system_record_import_contract(
        raw_contract=raw_contract,
        tenant_id=user.tenant_id,
        domain_id=domain_id,
        db=db,
    )
    return preview_system_record_csv(content, contract)


@app.post("/api/v1/admin/system-record-import-mappings", status_code=201)
async def submit_system_record_import_mapping(
    request: SystemRecordImportMappingRequest,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.RULE_AUTHOR])),
    db: AsyncSession = Depends(get_db_session),
):
    """Submit a reusable CSV mapping for review, retaining configuration only."""

    ensure_domain_access(user, request.domain_id)
    contract = await validated_system_record_import_contract(
        raw_contract=request.contract,
        tenant_id=user.tenant_id,
        domain_id=request.domain_id,
        db=db,
    )
    contract_document = contract.model_dump(mode="json")
    contract_sha256 = hashlib.sha256(
        json.dumps(contract_document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    try:
        return await SystemRecordImportMappingRepository(db).create(
            mapping_id="mapping_" + uuid.uuid4().hex,
            tenant_id=user.tenant_id,
            domain_id=request.domain_id,
            mapping_name=contract.mapping_id,
            source_system=contract.source_system,
            contract=contract_document,
            contract_sha256=contract_sha256,
            author_id=user.user_id,
        )
    except SystemRecordImportMappingConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/v1/admin/system-record-import-mappings")
async def list_system_record_import_mappings(
    domain_id: str,
    status: Optional[Literal["PENDING", "APPROVED", "REJECTED"]] = None,
    user: UserIdentity = Depends(require_role([
        Role.TENANT_ADMIN,
        Role.RULE_AUTHOR,
        Role.RULE_APPROVER,
        Role.AUDITOR,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    """List submitted mapping configurations for an assigned decision domain."""

    ensure_domain_access(user, domain_id)
    return {
        "items": await SystemRecordImportMappingRepository(db).list_for_domain(
            tenant_id=user.tenant_id,
            domain_id=domain_id,
            status=status,
        ),
        "can_submit": user.role in {Role.TENANT_ADMIN, Role.RULE_AUTHOR},
        "can_review": user.role in {Role.TENANT_ADMIN, Role.RULE_APPROVER},
    }


@app.get("/api/v1/admin/system-record-import-mappings/{mapping_id}/history")
async def get_system_record_import_mapping_history(
    mapping_id: str,
    domain_id: str,
    user: UserIdentity = Depends(require_role([
        Role.TENANT_ADMIN,
        Role.RULE_AUTHOR,
        Role.RULE_APPROVER,
        Role.AUDITOR,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    """Return the immutable event trail for a submitted mapping."""

    ensure_domain_access(user, domain_id)
    events = await SystemRecordImportMappingRepository(db).list_events(
        mapping_id=mapping_id,
        tenant_id=user.tenant_id,
        domain_id=domain_id,
    )
    if events is None:
        raise HTTPException(status_code=404, detail="System-record import mapping was not found.")
    return {"items": events}


@app.post("/api/v1/admin/system-record-import-mappings/{mapping_id}/approve")
async def approve_system_record_import_mapping(
    mapping_id: str,
    request: SystemRecordImportMappingApprovalRequest,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.RULE_APPROVER])),
    db: AsyncSession = Depends(get_db_session),
):
    """Approve an immutable configuration; authors cannot approve their own work."""

    ensure_domain_access(user, request.domain_id)
    try:
        mapping = await SystemRecordImportMappingRepository(db).review(
            mapping_id=mapping_id,
            tenant_id=user.tenant_id,
            domain_id=request.domain_id,
            reviewer_id=user.user_id,
            approved=True,
            note=request.note,
        )
    except SystemRecordImportMappingConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if mapping is None:
        raise HTTPException(status_code=404, detail="System-record import mapping was not found.")
    return mapping


@app.post("/api/v1/admin/system-record-import-mappings/{mapping_id}/reject")
async def reject_system_record_import_mapping(
    mapping_id: str,
    request: SystemRecordImportMappingRejectionRequest,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.RULE_APPROVER])),
    db: AsyncSession = Depends(get_db_session),
):
    """Reject a mapping with an auditable reason; it cannot be edited in place."""

    ensure_domain_access(user, request.domain_id)
    try:
        mapping = await SystemRecordImportMappingRepository(db).review(
            mapping_id=mapping_id,
            tenant_id=user.tenant_id,
            domain_id=request.domain_id,
            reviewer_id=user.user_id,
            approved=False,
            note=request.reason,
        )
    except SystemRecordImportMappingConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if mapping is None:
        raise HTTPException(status_code=404, detail="System-record import mapping was not found.")
    return mapping


@app.post("/api/v1/governance/handbook-upload-sessions", status_code=201)
async def create_handbook_upload_session(
    request: HandbookUploadSessionRequest,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.RULE_AUTHOR])),
    db: AsyncSession = Depends(get_db_session),
):
    """Issues a constrained direct-upload contract without queuing a policy change."""
    ensure_domain_access(user, request.domain_id)
    file_name, content_type = handbook_source_metadata(request.file_name, request.content_type)
    maximum_size = handbook_direct_upload_max_bytes()
    if request.file_size_bytes > maximum_size:
        raise HTTPException(status_code=413, detail="Handbook exceeds the configured direct upload size limit.")
    if not BlobStorage.direct_uploads_available():
        raise HTTPException(status_code=503, detail="Direct handbook uploads are not configured for this environment.")

    ttl_seconds = handbook_upload_session_ttl_seconds()
    session_id = f"handbook_session_{uuid.uuid4().hex}"
    storage_key = f"{BlobStorage.tenant_prefix(user.tenant_id)}/handbook-staging/{session_id}.pdf"
    try:
        upload_contract = await BlobStorage.create_presigned_post(
            tenant_id=user.tenant_id,
            key=storage_key,
            content_type=content_type,
            maximum_size=request.file_size_bytes,
            expires_in=ttl_seconds,
        )
        upload_session = await HandbookRepository(db).create_upload_session(
            session_id=session_id,
            tenant_id=user.tenant_id,
            domain_id=request.domain_id,
            file_name=file_name,
            content_type=content_type,
            file_size_bytes=request.file_size_bytes,
            storage_key=storage_key,
            uploaded_by=user.user_id,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
        )
    except HandbookUploadConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="The direct handbook upload service is unavailable.") from exc
    return {**upload_session, "upload_url": upload_contract["url"], "upload_fields": upload_contract["fields"]}


@app.post("/api/v1/governance/handbook-upload-sessions/{session_id}/complete", status_code=201)
async def complete_handbook_upload_session(
    session_id: str,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.RULE_AUTHOR])),
    db: AsyncSession = Depends(get_db_session),
):
    """Queues an object only after its storage metadata matches the upload session."""
    repository = HandbookRepository(db)
    try:
        upload_session = await repository.get_pending_upload_session(session_id, tenant_id=user.tenant_id)
        ensure_domain_access(user, cast(str, upload_session.domain_id))
        metadata = await BlobStorage.get_object_metadata(cast(str, upload_session.storage_key))
        if metadata["content_length"] != upload_session.file_size_bytes:
            raise HTTPException(status_code=422, detail="Uploaded handbook size does not match the approved upload session.")
        if metadata["content_type"] not in {upload_session.content_type, "application/x-pdf"}:
            raise HTTPException(status_code=422, detail="Uploaded handbook type does not match the approved upload session.")
        upload = await repository.complete_upload_session(
            upload_session,
            handbook_id=f"handbook_{uuid.uuid4().hex}",
        )
    except HandbookUploadConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        **upload,
        "next_step": "The extraction worker will create and hash an immutable review source; it cannot publish a policy.",
    }


@app.post("/api/v1/governance/handbooks", status_code=201)
async def upload_handbook(
    domain_id: str = Form(...),
    file: UploadFile = File(...),
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.RULE_AUTHOR])),
    db: AsyncSession = Depends(get_db_session),
):
    """Queues a verified PDF source; extraction happens only in a worker."""
    ensure_domain_access(user, domain_id)
    file_name, content_type = handbook_source_metadata(
        file.filename or "handbook.pdf",
        file.content_type or "application/pdf",
    )

    maximum_size = handbook_upload_max_bytes()
    total_size = 0
    source_hash = hashlib.sha256()
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b") as source_file:
        while chunk := await file.read(1024 * 1024):
            total_size += len(chunk)
            if total_size > maximum_size:
                raise HTTPException(status_code=413, detail="Handbook exceeds the configured upload size limit.")
            source_hash.update(chunk)
            source_file.write(chunk)
        if total_size == 0:
            raise HTTPException(status_code=422, detail="Handbook upload is empty.")
        content_hash = source_hash.hexdigest()
        storage_key = await BlobStorage.upload_binary(
            source_file,
            tenant_id=user.tenant_id,
            content_hash=content_hash,
            suffix=".pdf",
        )

    handbook_id = "handbook_" + uuid.uuid4().hex
    try:
        upload = await HandbookRepository(db).create_upload(
            handbook_id=handbook_id,
            tenant_id=user.tenant_id,
            domain_id=domain_id,
            file_name=file_name,
            content_type=content_type,
            file_size_bytes=total_size,
            content_hash=content_hash,
            storage_key=storage_key,
            uploaded_by=user.user_id,
        )
    except HandbookUploadConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {
        **upload,
        "next_step": "The extraction worker will create page-level review material; it cannot publish a policy.",
    }


@app.get("/api/v1/governance/handbooks")
async def list_handbook_uploads(
    user: UserIdentity = Depends(require_role([
        Role.TENANT_ADMIN,
        Role.RULE_AUTHOR,
        Role.RULE_APPROVER,
        Role.AUDITOR,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    domain_ids = None if user.role == Role.TENANT_ADMIN else user.domain_ids
    return {
        "items": await HandbookRepository(db).list_uploads(
            tenant_id=user.tenant_id,
            domain_ids=domain_ids,
        )
    }


@app.get("/api/v1/admin/background-jobs")
async def list_background_jobs(
    status: Literal["QUEUED", "RUNNING", "SUCCEEDED", "DEAD_LETTER"] | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN])),
    db: AsyncSession = Depends(get_db_session),
):
    """Expose identifier-only durable job state to the tenant operator."""
    try:
        items = await BackgroundJobRepository(db).list_jobs(
            tenant_id=user.tenant_id,
            status=status,
            limit=limit,
        )
    except BackgroundJobConflictError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"items": items}


@app.get("/api/v1/governance/handbooks/{handbook_id}/pages")
async def list_handbook_pages(
    handbook_id: str,
    after_page: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=25),
    user: UserIdentity = Depends(require_role([
        Role.TENANT_ADMIN,
        Role.RULE_AUTHOR,
        Role.RULE_APPROVER,
        Role.AUDITOR,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    """Returns bounded page excerpts for human source review, never extracted rules."""
    repository = HandbookRepository(db)
    upload = await repository.get_upload(handbook_id, tenant_id=user.tenant_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Handbook source was not found.")
    ensure_domain_access(user, cast(str, upload.domain_id))
    pages = await repository.list_page_excerpts(
        handbook_id=handbook_id,
        after_page=after_page,
        limit=limit,
    )
    has_next_page = len(pages) > limit
    return {
        "handbook_id": handbook_id,
        "file_name": upload.file_name,
        "status": upload.status,
        "items": pages[:limit],
        "next_page_after": pages[limit - 1]["page_number"] if has_next_page else None,
    }


@app.post("/api/v1/governance/handbooks/{handbook_id}/ocr", status_code=202)
async def request_handbook_ocr(
    handbook_id: str,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.RULE_AUTHOR])),
    db: AsyncSession = Depends(get_db_session),
):
    """Queues OCR proposals only for pages already held for manual review."""
    if not ocr_provider_is_configured():
        raise HTTPException(status_code=503, detail="OCR is not configured for this institution.")

    repository = HandbookRepository(db)
    try:
        existing = await repository.get_upload(handbook_id, tenant_id=user.tenant_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Handbook source was not found.")
        ensure_domain_access(user, cast(str, existing.domain_id))
        upload = await repository.queue_ocr(handbook_id, tenant_id=user.tenant_id)
    except HandbookUploadConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        **HandbookRepository._summary(upload),
        "next_step": "The OCR worker will create untrusted page proposals for staff review; it cannot alter a policy.",
    }


@app.get("/api/v1/governance/handbooks/{handbook_id}/ocr-reviews")
async def list_handbook_ocr_reviews(
    handbook_id: str,
    user: UserIdentity = Depends(require_role([
        Role.TENANT_ADMIN,
        Role.RULE_AUTHOR,
        Role.RULE_APPROVER,
        Role.AUDITOR,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    repository = HandbookRepository(db)
    upload = await repository.get_upload(handbook_id, tenant_id=user.tenant_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Handbook source was not found.")
    ensure_domain_access(user, cast(str, upload.domain_id))
    return {"items": await repository.list_ocr_reviews(handbook_id)}


@app.patch("/api/v1/governance/handbooks/{handbook_id}/ocr-reviews/{page_number}")
async def review_handbook_ocr(
    handbook_id: str,
    page_number: int,
    request: OCRReviewDecisionRequest,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.RULE_AUTHOR])),
    db: AsyncSession = Depends(get_db_session),
):
    """Promotes one reviewed OCR proposal to page text or rejects it with an audit event."""
    repository = HandbookRepository(db)
    upload = await repository.get_upload(handbook_id, tenant_id=user.tenant_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Handbook source was not found.")
    ensure_domain_access(user, cast(str, upload.domain_id))
    try:
        review = await repository.review_ocr_candidate(
            handbook_id=handbook_id,
            page_number=page_number,
            action=request.action,
            reviewed_text=request.reviewed_text,
            reviewer_id=user.user_id,
        )
    except HandbookUploadConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return review


@app.get("/api/v1/public/policy-guides")
async def list_public_policy_guides(
    db: AsyncSession = Depends(get_db_session),
):
    """Lists only approved policy guides explicitly made public by a tenant."""
    return {"items": await PublicAccessRepository(db).list_public_policy_guides()}


@app.get("/api/v1/public/policy-guides/{domain_id}")
async def get_public_policy_guide(
    domain_id: str,
    version: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
):
    """Returns a citation-bound policy guide, not a personalised decision."""
    try:
        return await PublicAccessRepository(db).get_public_policy_guide(domain_id, version)
    except PublicPolicyUnavailableError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/v1/public/policy-guides/{domain_id}/support", status_code=202)
async def request_public_policy_support(
    domain_id: str,
    support_request: PublicSupportRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """Records a human-assistance request; it never modifies evidence or facts."""
    await enforce_public_support_rate_limit(http_request, domain_id)
    try:
        request_id = "support_" + uuid.uuid4().hex
        with public_support_request_scope(request_id):
            await PublicAccessRepository(db).create_support_request(
                request_id=request_id,
                domain_id=domain_id,
                category=support_request.category,
                contact_details=support_request.contact_details.strip() if support_request.contact_details else None,
                message=support_request.message,
            )
    except PublicPolicyUnavailableError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"request_id": request_id, "status": "OPEN"}


@app.get("/api/v1/admin/support-requests")
async def list_support_requests(
    domain_id: str,
    limit: int = 50,
    user: UserIdentity = Depends(require_role([
        Role.TENANT_ADMIN,
        Role.AUDITOR,
        Role.ASSISTANCE_COORDINATOR,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    ensure_domain_access(user, domain_id)
    return {
        "items": await PublicAccessRepository(db).list_support_requests(
            tenant_id=user.tenant_id,
            domain_id=domain_id,
            limit=min(max(limit, 1), 200),
        )
    }


@app.patch("/api/v1/admin/support-requests/{request_id}")
async def update_support_request_status(
    request_id: str,
    update: SupportRequestStatusUpdate,
    user: UserIdentity = Depends(require_role([
        Role.TENANT_ADMIN,
        Role.ASSISTANCE_COORDINATOR,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    """Updates human follow-up workflow without touching policy or evidence."""
    ensure_domain_access(user, update.domain_id)
    support_request = await PublicAccessRepository(db).update_support_request_status(
        request_id=request_id,
        tenant_id=user.tenant_id,
        domain_id=update.domain_id,
        status=update.status,
        actor_id=user.user_id,
    )
    if support_request is None:
        raise HTTPException(status_code=404, detail="Assistance request was not found.")
    return support_request


@app.get("/api/v1/admin/support-requests/{request_id}/history")
async def list_support_request_history(
    request_id: str,
    domain_id: str,
    user: UserIdentity = Depends(require_role([
        Role.TENANT_ADMIN,
        Role.AUDITOR,
        Role.ASSISTANCE_COORDINATOR,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    """Returns append-only assistance workflow history for an assigned domain."""
    ensure_domain_access(user, domain_id)
    events = await PublicAccessRepository(db).list_support_request_events(
        request_id=request_id,
        tenant_id=user.tenant_id,
        domain_id=domain_id,
    )
    if events is None:
        raise HTTPException(status_code=404, detail="Assistance request was not found.")
    return {"items": events}


@app.post("/api/v1/decision-reviews", status_code=201)
async def submit_decision_review(
    submission: DecisionReviewSubmission,
    user: UserIdentity = Depends(require_role([Role.SUBJECT])),
    db: AsyncSession = Depends(get_db_session),
):
    """Opens a subject-owned review case without changing the original decision."""
    ensure_domain_access(user, submission.domain_id)
    reasoning_repository = ReasoningRepository(db)
    trace = await reasoning_repository.get_reasoning_graph(
        submission.reasoning_graph_id,
        tenant_id=user.tenant_id,
    )
    if trace is None or trace.evaluation_context is None:
        raise HTTPException(status_code=404, detail="Decision trace was not found.")
    if trace.evaluation_context.domain_id != submission.domain_id:
        raise HTTPException(status_code=409, detail="Decision trace belongs to a different domain.")
    ensure_subject_access(user, trace.subject_id)

    evidence_repository = EvidenceRepository(db)
    for evidence_id in submission.submitted_evidence_ids:
        stored_evidence = await evidence_repository.get_evidence(evidence_id, tenant_id=user.tenant_id)
        if stored_evidence is None:
            raise HTTPException(status_code=422, detail="Submitted evidence was not found for this institution.")
        if (
            stored_evidence.domain_id != submission.domain_id
            or stored_evidence.evidence.subject_id != trace.subject_id
        ):
            raise HTTPException(status_code=409, detail="Submitted evidence does not belong to this decision review.")

    try:
        review_case = await DecisionReviewRepository(db).create_case(
            case_id="review_" + uuid.uuid4().hex,
            tenant_id=user.tenant_id,
            domain_id=submission.domain_id,
            subject_id=trace.subject_id,
            reasoning_graph_id=submission.reasoning_graph_id,
            category=submission.category,
            message=submission.message,
            disputed_fact_paths=submission.disputed_fact_paths,
            submitted_evidence_ids=submission.submitted_evidence_ids,
            actor_id=user.user_id,
        )
    except DecisionReviewUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DecisionReviewConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return review_case


@app.get("/api/v1/decision-reviews")
async def list_decision_reviews(
    domain_id: Optional[str] = None,
    limit: int = 50,
    user: UserIdentity = Depends(require_role([
        Role.SUBJECT,
        Role.TENANT_ADMIN,
        Role.ASSISTANCE_COORDINATOR,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    """Lists a subject's own cases or staff cases for one assigned domain."""
    repository = DecisionReviewRepository(db)
    if user.role == Role.SUBJECT:
        if not user.subject_id:
            raise HTTPException(status_code=401, detail="Subject identity is missing from the access token.")
        if domain_id:
            ensure_domain_access(user, domain_id)
        return {
            "items": await repository.list_cases(
                tenant_id=user.tenant_id,
                domain_id=domain_id,
                subject_id=user.subject_id,
                limit=min(max(limit, 1), 200),
            )
        }
    if not domain_id:
        raise HTTPException(status_code=422, detail="Staff review lists require a domain identifier.")
    ensure_domain_access(user, domain_id)
    return {
        "items": await repository.list_cases(
            tenant_id=user.tenant_id,
            domain_id=domain_id,
            subject_id=None,
            limit=min(max(limit, 1), 200),
        )
    }


@app.get("/api/v1/decision-reviews/{review_case_id}")
async def get_decision_review(
    review_case_id: str,
    user: UserIdentity = Depends(require_role([
        Role.SUBJECT,
        Role.TENANT_ADMIN,
        Role.ASSISTANCE_COORDINATOR,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    review_case = await DecisionReviewRepository(db).get_case(
        review_case_id,
        tenant_id=user.tenant_id,
    )
    if review_case is None:
        raise HTTPException(status_code=404, detail="Decision review case was not found.")
    ensure_decision_review_case_access(user, review_case)
    return review_case


@app.get("/api/v1/decision-reviews/{review_case_id}/history")
async def get_decision_review_history(
    review_case_id: str,
    user: UserIdentity = Depends(require_role([
        Role.SUBJECT,
        Role.TENANT_ADMIN,
        Role.ASSISTANCE_COORDINATOR,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    repository = DecisionReviewRepository(db)
    review_case = await repository.get_case(review_case_id, tenant_id=user.tenant_id)
    if review_case is None:
        raise HTTPException(status_code=404, detail="Decision review case was not found.")
    ensure_decision_review_case_access(user, review_case)
    events = await repository.list_case_events(case_id=review_case_id, tenant_id=user.tenant_id)
    return {"items": events or []}


@app.patch("/api/v1/admin/decision-reviews/{review_case_id}")
async def update_decision_review(
    review_case_id: str,
    update: DecisionReviewCaseUpdate,
    user: UserIdentity = Depends(require_role([
        Role.TENANT_ADMIN,
        Role.ASSISTANCE_COORDINATOR,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    """Records a human resolution; it cannot mutate evidence, policy, or the original trace."""
    ensure_domain_access(user, update.domain_id)
    try:
        review_case = await DecisionReviewRepository(db).update_case(
            case_id=review_case_id,
            tenant_id=user.tenant_id,
            domain_id=update.domain_id,
            status=update.status,
            actor_id=user.user_id,
            resolution=update.resolution,
            response_message=update.response_message,
        )
    except DecisionReviewConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if review_case is None:
        raise HTTPException(status_code=404, detail="Decision review case was not found.")
    return review_case

@app.get("/api/v1/admin/permissions")
async def get_admin_permissions(
    domain_id: str,
    user: UserIdentity = Depends(require_role([
        Role.TENANT_ADMIN,
        Role.METADATA_STEWARD,
        Role.AUDITOR,
    ])),
    registry: EdgeRegistry = Depends(get_edge_registry),
):
    """
    Returns the governance matrix and the selected domain's Edge-configured
    metadata surface.
    It is limited to governance staff because it exposes the institution's
    configured metadata surface and role matrix.
    """
    ensure_domain_access(user, domain_id)
    try:
        policy = registry.get_governance_policy(user.tenant_id, domain_id)
    except DomainConfigurationError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {
        "current_role": user.role.value,
        "domain_id": domain_id,
        "metadata_quick_edits": [
            target.model_dump() for target in policy.metadata_quick_edits
        ],
        "review_required_changes": policy.review_required_changes,
        "formal_governance_changes": policy.formal_governance_changes,
        "matrix": get_role_permission_matrix(),
    }

@app.post("/api/v1/admin/quick-edit", status_code=201)
async def apply_quick_edit(
    request: QuickEditRequest,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.METADATA_STEWARD])),
    db: AsyncSession = Depends(get_db_session),
    registry: EdgeRegistry = Depends(get_edge_registry),
):
    """
    Applies a Tier 1 metadata correction immediately and records an immutable
    audit event. Allowed targets and fields come from the selected Edge domain,
    never from runtime code.
    """
    ensure_domain_access(user, request.domain_id)
    try:
        policy = registry.get_governance_policy(user.tenant_id, request.domain_id)
    except DomainConfigurationError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    field_policy = policy.get_quick_edit_field(request.target_type, request.field)
    if field_policy is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{request.target_type}.{request.field} is not configured as a "
                "low-risk metadata quick edit for this domain."
            ),
        )

    repo = MetadataGovernanceRepository(db)
    try:
        result = await repo.apply_quick_edit(
            edit_id="qe_" + uuid.uuid4().hex,
            tenant_id=user.tenant_id,
            domain_id=request.domain_id,
            target_type=request.target_type,
            target_id=request.target_id,
            field_name=request.field,
            submitted_old_value=request.old_value,
            new_value=request.new_value,
            reason=request.reason,
            source_reference=request.source_reference,
            actor_id=user.user_id,
            actor_role=user.role.value,
        )
    except QuickEditConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {
        **result,
        "field_policy": field_policy.model_dump(),
    }

@app.post("/api/v1/admin/quick-edits", status_code=201)
async def apply_quick_edit_plural(
    request: QuickEditRequest,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.METADATA_STEWARD])),
    db: AsyncSession = Depends(get_db_session),
    registry: EdgeRegistry = Depends(get_edge_registry),
):
    """Plural alias for REST clients that prefer collection-style paths."""
    return await apply_quick_edit(request, user, db, registry)

@app.get("/api/v1/admin/quick-edits")
async def list_quick_edit_audit_log(
    domain_id: str,
    target_id: Optional[str] = None,
    limit: int = 50,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.METADATA_STEWARD, Role.AUDITOR])),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Lists Tier 1 quick-edit audit events for the authenticated tenant.
    """
    ensure_domain_access(user, domain_id)
    bounded_limit = min(max(limit, 1), 200)
    repo = MetadataGovernanceRepository(db)
    return {
        "items": await repo.list_quick_edits(
            tenant_id=user.tenant_id,
            domain_id=domain_id,
            target_id=target_id,
            limit=bounded_limit,
        )
    }

@app.get("/api/v1/admin/metadata-overrides")
async def list_metadata_overrides(
    domain_id: str,
    target_id: Optional[str] = None,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.METADATA_STEWARD, Role.AUDITOR])),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Returns the currently applied Tier 1 metadata overlay.
    """
    ensure_domain_access(user, domain_id)
    repo = MetadataGovernanceRepository(db)
    return {
        "items": await repo.list_metadata_overrides(
            tenant_id=user.tenant_id,
            domain_id=domain_id,
            target_id=target_id,
        )
    }

@app.post("/api/v1/governance/policy-ambiguities", status_code=201)
async def raise_policy_ambiguity(
    request: PolicyAmbiguityRequest,
    user: UserIdentity = Depends(require_role([
        Role.TENANT_ADMIN,
        Role.RULE_AUTHOR,
        Role.POLICY_OWNER,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    """Records an unresolved interpretation instead of hiding it in a draft."""
    ensure_domain_access(user, request.domain_id)
    try:
        await acquire_domain_governance_lock(db, request.domain_id)
    except GovernancePublicationBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    record = await PolicyAmbiguityRepository(db).create(
        ambiguity_id="amb_" + uuid.uuid4().hex,
        tenant_id=user.tenant_id,
        domain_id=request.domain_id,
        source_citation=request.source_citation,
        question=request.question,
        interpretation_options=request.interpretation_options,
        created_by=user.user_id,
    )
    return record


@app.get("/api/v1/governance/policy-ambiguities")
async def list_policy_ambiguities(
    domain_id: str,
    status: Optional[Literal["OPEN", "RESOLVED"]] = None,
    user: UserIdentity = Depends(require_role([
        Role.TENANT_ADMIN,
        Role.RULE_AUTHOR,
        Role.RULE_APPROVER,
        Role.POLICY_OWNER,
        Role.AUDITOR,
    ])),
    db: AsyncSession = Depends(get_db_session),
):
    """Lists the interpretation register for an assigned policy domain."""
    ensure_domain_access(user, domain_id)
    return {
        "items": await PolicyAmbiguityRepository(db).list_for_domain(
            tenant_id=user.tenant_id,
            domain_id=domain_id,
            status=status,
        )
    }


@app.patch("/api/v1/governance/policy-ambiguities/{ambiguity_id}/resolve")
async def resolve_policy_ambiguity(
    ambiguity_id: str,
    request: PolicyAmbiguityResolutionRequest,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.POLICY_OWNER])),
    db: AsyncSession = Depends(get_db_session),
):
    """Records the authorised interpretation and its source, append-only."""
    ensure_domain_access(user, request.domain_id)
    try:
        await acquire_domain_governance_lock(db, request.domain_id)
        record = await PolicyAmbiguityRepository(db).resolve(
            ambiguity_id=ambiguity_id,
            tenant_id=user.tenant_id,
            domain_id=request.domain_id,
            resolution=request.resolution,
            source_reference=request.source_reference,
            actor_id=user.user_id,
        )
    except (PolicyAmbiguityConflictError, GovernancePublicationBusyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Policy ambiguity was not found.")
    return record


@app.post("/api/v1/governance/releases", status_code=201)
async def release_policy(
    request: ReleasePolicyRequest,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.RULE_APPROVER])),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Reviews and publishes a draft as an immutable, signed Release.

    Enforces separation of duties: the approver must be a different
    identity than the draft's author. This is checked here, not left as a
    comment, because it's the entire reason a Release is trustworthy.
    """
    draft_repo = DraftRepository(db)
    release_repo = ReleaseRepository(db)

    draft = await draft_repo.get_draft(request.draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found.")

    if draft.tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Draft belongs to a different tenant.")

    if draft.status != "PENDING":
        raise HTTPException(status_code=409, detail=f"Draft is already {draft.status}, not releasable.")

    ensure_domain_access(user, draft.domain_id)

    if draft.author_id == user.user_id:
        raise HTTPException(
            status_code=403,
            detail="Separation of duties violation: the approver cannot be the same identity as the author."
        )

    try:
        await acquire_domain_governance_lock(db, draft.domain_id)
    except GovernancePublicationBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if await release_repo.get_release(draft.domain_id, request.version):
        raise HTTPException(
            status_code=409,
            detail=f"Release version {request.version} already exists for this domain.",
        )

    ambiguity_repo = PolicyAmbiguityRepository(db)
    if await ambiguity_repo.has_open_ambiguities(
        tenant_id=user.tenant_id,
        domain_id=draft.domain_id,
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "This domain has unresolved policy ambiguities. Record an authorised interpretation "
                "with its source before publishing a release."
            ),
        )

    try:
        release_id = "rel_" + uuid.uuid4().hex
        rule_graph = compile_release_to_graph(release_id, draft.payload)
    except (ValueError, UnsupportedOperatorError) as e:
        raise HTTPException(status_code=422, detail=f"Draft failed compilation, cannot be released: {str(e)}")

    applicability = {
        criterion.attribute: criterion.values
        for criterion in request.applicability
    }
    # The signature covers identity, scheduling, applicability, and rule logic.
    # Otherwise a policy could be re-scoped without invalidating its signature.
    signature_payload = {
        "policy": draft.payload,
        "release": {
            "id": release_id,
            "domain_id": draft.domain_id,
            "version": request.version,
            "rule_graph_id": rule_graph.id,
            "effective_from": request.effective_from.isoformat(),
            "effective_until": request.effective_until.isoformat() if request.effective_until else None,
            "applicability": applicability,
        },
    }
    crypto = CryptoService()
    signature_hex, _hash_hex = crypto.sign_payload(signature_payload)

    release = Release(
        id=release_id,
        domain_id=draft.domain_id,
        version=request.version,
        rule_graph_id=rule_graph.id,
        digital_signature=signature_hex,
        signed_payload=signature_payload,
        signed_payload_hash=_hash_hex,
        signing_key_id=crypto.key_id,
        signing_public_key=crypto.public_key_pem,
        effective_from=request.effective_from,
        effective_until=request.effective_until,
        applicability=applicability,
    )
    try:
        await release_repo.create_release(
            release,
            rule_graph,
            draft.payload["root"],
            draft_id=draft.id,
        )
    except (
        DraftReleaseConflictError,
        ReleaseVersionConflictError,
        ReleaseApplicabilityConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {
        "release_id": release.id,
        "domain_id": release.domain_id,
        "version": release.version,
        "rule_graph_id": release.rule_graph_id,
        "effective_from": release.effective_from,
        "effective_until": release.effective_until,
        "applicability": release.applicability,
        "signing_key_id": release.signing_key_id,
        "signed_payload_hash": release.signed_payload_hash,
        "approved_by": user.user_id,
        "authored_by": draft.author_id
    }


@app.get("/api/v1/governance/releases/{domain_id}/{version}/integrity")
async def verify_release_integrity(
    domain_id: str,
    version: str,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.AUDITOR])),
    db: AsyncSession = Depends(get_db_session),
):
    """Verifies a release from its persisted public-key verification bundle."""
    ensure_domain_access(user, domain_id)
    release = await ReleaseRepository(db).get_release(domain_id, version)
    if release is None:
        raise HTTPException(status_code=404, detail="Release was not found.")
    rule_graph = await ReleaseRepository(db).get_compiled_rule_graph(release.rule_graph_id)
    if rule_graph is None:
        valid, reason = False, "persisted compiled graph is unavailable"
    else:
        valid, reason = verify_release_bundle(release, rule_graph)
    if not valid and reason == "release has no complete signing verification bundle":
        raise HTTPException(
            status_code=409,
            detail="This legacy release does not retain a complete verification bundle.",
        )
    return {
        "release_id": release.id,
        "domain_id": release.domain_id,
        "version": release.version,
        "signing_key_id": release.signing_key_id,
        "signed_payload_hash": release.signed_payload_hash,
        "signature_valid": valid,
        "verification_reason": reason,
    }
         
@app.get("/api/v1/replay/{graph_id}")
async def replay_evaluation(
    graph_id: str,
    user: UserIdentity = Depends(require_role([Role.TENANT_ADMIN, Role.AUDITOR])),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Gathers all data needed to replay an evaluation.
    """
    # For now, just return the reasoning graph so the e2e test can check it
    repo = ReasoningRepository(db)
    
    payload = await repo.get_reasoning_graph(graph_id, tenant_id=user.tenant_id)
    if not payload:
         raise HTTPException(status_code=404, detail="Reasoning graph not found")
    if not payload.evaluation_context:
        raise HTTPException(status_code=409, detail="Reasoning graph lacks replayable evaluation context.")
    ensure_domain_access(user, payload.evaluation_context.domain_id)
         
    return payload.model_dump()

@app.get("/api/v1/claims")
async def get_claims(
    graph_id: str,
    user: UserIdentity = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Retrieves extracted claims for a tenant-scoped reasoning graph."""
    repo = ReasoningRepository(db)
    graph = await repo.get_reasoning_graph(graph_id, tenant_id=user.tenant_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Reasoning graph not found")
    if not graph.evaluation_context:
        raise HTTPException(status_code=409, detail="Reasoning graph lacks replayable evaluation context.")
    ensure_domain_access(user, graph.evaluation_context.domain_id)
    ensure_subject_access(user, graph.subject_id)
    return {"items": [claim.model_dump() for claim in await repo.get_claims(graph_id, tenant_id=user.tenant_id)]}

@app.get("/api/v1/facts")
async def get_facts(
    graph_id: str,
    user: UserIdentity = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Retrieves accepted facts for a tenant-scoped reasoning graph."""
    repo = ReasoningRepository(db)
    graph = await repo.get_reasoning_graph(graph_id, tenant_id=user.tenant_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Reasoning graph not found")
    if not graph.evaluation_context:
        raise HTTPException(status_code=409, detail="Reasoning graph lacks replayable evaluation context.")
    ensure_domain_access(user, graph.evaluation_context.domain_id)
    ensure_subject_access(user, graph.subject_id)
    return {"items": [fact.model_dump() for fact in await repo.get_facts(graph_id, tenant_id=user.tenant_id)]}
