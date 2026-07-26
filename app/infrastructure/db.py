"""
Database Schema Definition.

Proves the transition from the filesystem to a relational database.
Maps the Core Domain Models into SQLAlchemy ORM tables for Postgres.
"""

from typing import Any

from sqlalchemy import CheckConstraint, Column, String, Float, Integer, Date, DateTime, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.types import TypeDecorator, JSON

# Dynamically support PostgreSQL JSONB for indexing while keeping SQLite fallback
from sqlalchemy.dialects.postgresql import JSONB

class JSONType(TypeDecorator):
    """
    Safely routes JSON column types.
    Uses native JSONB on Postgres for raw performance and indexability.
    Falls back to stringified JSON on SQLite.
    """
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(JSONB())
        else:
            return dialect.type_descriptor(JSON())

Base: Any = declarative_base()

class DBTenant(Base):
    __tablename__ = 'tenants'
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DBDomain(Base):
    __tablename__ = 'domains'
    id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey('tenants.id'), nullable=False)
    name = Column(String, nullable=False)
    schema_definition = Column(JSONType, nullable=False)

class DBPolicyDraft(Base):
    """
    A proposed rule change awaiting review. Mutable while PENDING -- becomes
    irrelevant (never edited) once RELEASED or REJECTED; a correction after
    that point is a new draft, not a change to this row.
    """
    __tablename__ = 'policy_drafts'
    id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey('tenants.id'), nullable=False)
    domain_id = Column(String, ForeignKey('domains.id'), nullable=False)
    policy_name = Column(String, nullable=False)
    author_id = Column(String, nullable=False)
    payload = Column(JSONType, nullable=False)
    status = Column(String, nullable=False, default="PENDING")  # PENDING | RELEASED | REJECTED
    released_as_release_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DBPolicyAmbiguity(Base):
    """A governed unresolved interpretation that must be settled before release."""
    __tablename__ = 'policy_ambiguities'

    id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey('tenants.id'), nullable=False, index=True)
    domain_id = Column(String, ForeignKey('domains.id'), nullable=False, index=True)
    source_citation = Column(Text, nullable=False)
    question = Column(Text, nullable=False)
    interpretation_options = Column(JSONType, nullable=False)
    status = Column(String, nullable=False, default="OPEN", index=True)
    resolution = Column(Text, nullable=True)
    resolution_source_reference = Column(Text, nullable=True)
    resolved_by = Column(String, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DBPolicyAmbiguityEvent(Base):
    """Append-only history for an ambiguity and its formal interpretation."""
    __tablename__ = 'policy_ambiguity_events'
    __table_args__ = (
        UniqueConstraint('ambiguity_id', 'sequence', name='uq_policy_ambiguity_event_sequence'),
    )

    id = Column(String, primary_key=True)
    ambiguity_id = Column(String, ForeignKey('policy_ambiguities.id'), nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    event_type = Column(String, nullable=False)
    actor_id = Column(String, nullable=False)
    resolution = Column(Text, nullable=True)
    source_reference = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DBHandbookUpload(Base):
    """Immutable handbook source and progress state for asynchronous extraction."""
    __tablename__ = 'handbook_uploads'
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    file_name = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    # Direct uploads receive their authoritative hash in the extraction worker.
    content_hash = Column(String, nullable=True, index=True)
    storage_key = Column(String, nullable=False)
    uploaded_by = Column(String, nullable=False)
    status = Column(String, nullable=False, default="QUEUED")
    total_pages = Column(Integer, nullable=True)
    processed_pages = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class DBHandbookUploadSession(Base):
    """Short-lived authority to place one handbook object in a staging key."""
    __tablename__ = 'handbook_upload_sessions'
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    file_name = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    storage_key = Column(String, nullable=False, unique=True)
    uploaded_by = Column(String, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DBBackgroundJob(Base):
    """Tenant-scoped durable work item with a bounded retry lifecycle."""
    __tablename__ = 'background_jobs'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'deduplication_key', name='uq_background_job_deduplication'),
        CheckConstraint(
            "job_type IN ('HANDBOOK_TEXT_EXTRACTION', 'HANDBOOK_OCR')",
            name='ck_background_job_type',
        ),
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'DEAD_LETTER')",
            name='ck_background_job_status',
        ),
        CheckConstraint('attempts >= 0', name='ck_background_job_attempts'),
        CheckConstraint('max_attempts BETWEEN 1 AND 10', name='ck_background_job_max_attempts'),
    )

    id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey('tenants.id'), nullable=False, index=True)
    domain_id = Column(String, ForeignKey('domains.id'), nullable=False, index=True)
    job_type = Column(String, nullable=False)
    resource_id = Column(String, nullable=False)
    # This is deliberately an identifier-only key: never persist source text or
    # subject evidence in a queue record.
    deduplication_key = Column(String, nullable=False)
    status = Column(String, nullable=False, default='QUEUED', index=True)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    available_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    locked_by = Column(String, nullable=True)
    last_error = Column(Text, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DBHandbookPage(Base):
    """Page-level extraction checkpoint; it is never a policy rule by itself."""
    __tablename__ = 'handbook_pages'
    __table_args__ = (
        UniqueConstraint('handbook_id', 'page_number', name='uq_handbook_page_number'),
    )
    id = Column(String, primary_key=True)
    handbook_id = Column(String, ForeignKey('handbook_uploads.id'), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    text_content = Column(Text, nullable=False)
    content_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class DBHandbookOcrReview(Base):
    """Untrusted OCR text for a source page, awaiting a staff review decision."""
    __tablename__ = 'handbook_ocr_reviews'
    __table_args__ = (
        UniqueConstraint('handbook_id', 'page_number', name='uq_handbook_ocr_review_page'),
    )
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    handbook_id = Column(String, ForeignKey('handbook_uploads.id'), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    provider_name = Column(String, nullable=False)
    provider_reference = Column(String, nullable=True)
    proposed_text = Column(Text, nullable=False)
    proposed_text_hash = Column(String, nullable=False)
    status = Column(String, nullable=False, default="PENDING_REVIEW")
    reviewed_text = Column(Text, nullable=True)
    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DBHandbookOcrReviewEvent(Base):
    """Append-only audit history for a decision about an OCR proposal."""
    __tablename__ = 'handbook_ocr_review_events'
    __table_args__ = (
        UniqueConstraint('ocr_review_id', 'sequence', name='uq_handbook_ocr_review_event_sequence'),
    )
    id = Column(String, primary_key=True)
    ocr_review_id = Column(String, ForeignKey('handbook_ocr_reviews.id'), nullable=False, index=True)
    action = Column(String, nullable=False)
    actor_id = Column(String, nullable=False)
    text_hash = Column(String, nullable=True)
    sequence = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DBMetadataOverride(Base):
    """
    Current Tier 1 metadata value for an Edge-defined resource.
    This is deliberately separate from RuleGraph releases: quick edits can
    correct low-risk presentation metadata without changing policy.
    """
    __tablename__ = 'metadata_overrides'
    __table_args__ = (
        UniqueConstraint(
            'tenant_id',
            'domain_id',
            'target_type',
            'target_id',
            'field_name',
            name='uq_metadata_override_target_field'
        ),
        Index(
            'ix_metadata_overrides_lookup',
            'tenant_id',
            'domain_id',
            'target_type',
            'target_id',
        ),
    )

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    domain_id = Column(String, nullable=False)
    target_type = Column(String, nullable=False)
    target_id = Column(String, nullable=False)
    field_name = Column(String, nullable=False)
    current_value = Column(Text, nullable=False)
    updated_by = Column(String, nullable=False)
    last_edit_id = Column(String, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class DBMetadataQuickEdit(Base):
    """
    Append-only audit trail for Tier 1 changes.
    Every quick edit is recorded even when it overwrites a previous metadata
    override, preserving who changed what, when, and why.
    """
    __tablename__ = 'metadata_quick_edits'
    __table_args__ = (
        Index('ix_metadata_quick_edits_tenant_domain', 'tenant_id', 'domain_id'),
    )

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    domain_id = Column(String, nullable=False)
    target_type = Column(String, nullable=False)
    target_id = Column(String, nullable=False)
    field_name = Column(String, nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    source_reference = Column(String, nullable=True)
    actor_id = Column(String, nullable=False)
    actor_role = Column(String, nullable=False)
    applied_at = Column(DateTime(timezone=True), server_default=func.now())


class DBSystemRecordImportMapping(Base):
    """A reviewed, versioned CSV mapping with no imported subject records."""
    __tablename__ = 'system_record_import_mappings'
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name='ck_system_record_import_mapping_status',
        ),
        CheckConstraint(
            "length(contract_sha256) = 64",
            name='ck_system_record_import_mapping_contract_hash',
        ),
        CheckConstraint(
            "(status = 'PENDING' AND reviewed_by IS NULL AND reviewed_at IS NULL) "
            "OR (status IN ('APPROVED', 'REJECTED') AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name='ck_system_record_import_mapping_review_state',
        ),
        CheckConstraint(
            "status <> 'REJECTED' OR review_note IS NOT NULL",
            name='ck_system_record_import_mapping_rejection_note',
        ),
        Index('ix_system_record_import_mappings_tenant_domain_status', 'tenant_id', 'domain_id', 'status'),
    )

    id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey('tenants.id'), nullable=False, index=True)
    domain_id = Column(String, ForeignKey('domains.id'), nullable=False, index=True)
    mapping_name = Column(String, nullable=False)
    source_system = Column(String, nullable=False)
    contract = Column(JSONType, nullable=False)
    contract_sha256 = Column(String, nullable=False)
    author_id = Column(String, nullable=False)
    status = Column(String, nullable=False, default='PENDING', index=True)
    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DBSystemRecordImportMappingEvent(Base):
    """Append-only review trail for an import mapping configuration."""
    __tablename__ = 'system_record_import_mapping_events'
    __table_args__ = (
        UniqueConstraint('mapping_id', 'sequence', name='uq_system_record_import_mapping_event_sequence'),
        CheckConstraint(
            "event_type IN ('SUBMITTED', 'APPROVED', 'REJECTED')",
            name='ck_system_record_import_mapping_event_type',
        ),
    )

    id = Column(String, primary_key=True)
    mapping_id = Column(String, ForeignKey('system_record_import_mappings.id'), nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    event_type = Column(String, nullable=False)
    actor_id = Column(String, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DBShadowCalibrationSuite(Base):
    """A non-operative comparison of a signed release with recorded outcomes."""
    __tablename__ = 'shadow_calibration_suites'
    __table_args__ = (
        CheckConstraint(
            "status IN ('SUBMITTED', 'CERTIFIED', 'COMPLETED')",
            name='ck_shadow_calibration_suite_status',
        ),
        CheckConstraint(
            "data_basis IN ('SYNTHETIC', 'APPROVED_DEIDENTIFIED')",
            name='ck_shadow_calibration_suite_data_basis',
        ),
    )

    id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey('tenants.id'), nullable=False, index=True)
    domain_id = Column(String, ForeignKey('domains.id'), nullable=False, index=True)
    release_id = Column(String, ForeignKey('releases.id'), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    data_basis = Column(String, nullable=False)
    privacy_approval_reference = Column(String, nullable=True)
    policy_as_of_date = Column(Date, nullable=False)
    author_id = Column(String, nullable=False)
    status = Column(String, nullable=False, default="SUBMITTED", index=True)
    input_sha256 = Column(String, nullable=False)
    certified_by = Column(String, nullable=True)
    certification_note = Column(Text, nullable=True)
    certified_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DBShadowCalibrationCase(Base):
    """One non-identifying representative case, immutable after submission."""
    __tablename__ = 'shadow_calibration_cases'
    __table_args__ = (
        UniqueConstraint('suite_id', 'case_reference', name='uq_shadow_calibration_case_reference'),
        CheckConstraint(
            "recorded_decision IN ('ELIGIBLE', 'INELIGIBLE', 'NEEDS_MANUAL_REVIEW')",
            name='ck_shadow_calibration_case_recorded_decision',
        ),
    )

    id = Column(String, primary_key=True)
    suite_id = Column(String, ForeignKey('shadow_calibration_suites.id'), nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    case_reference = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    recorded_decision = Column(String, nullable=False)
    recorded_outcome_reference = Column(Text, nullable=False)
    facts = Column(JSONType, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DBShadowCalibrationSuiteEvent(Base):
    """Append-only evidence for submission, certification, and completion."""
    __tablename__ = 'shadow_calibration_suite_events'
    __table_args__ = (
        UniqueConstraint('suite_id', 'sequence', name='uq_shadow_calibration_suite_event_sequence'),
        CheckConstraint(
            "event_type IN ('SUBMITTED', 'CERTIFIED', 'COMPLETED')",
            name='ck_shadow_calibration_suite_event_type',
        ),
    )

    id = Column(String, primary_key=True)
    suite_id = Column(String, ForeignKey('shadow_calibration_suites.id'), nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    event_type = Column(String, nullable=False)
    actor_id = Column(String, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DBShadowCalibrationRun(Base):
    """The single immutable report produced from one certified calibration suite."""
    __tablename__ = 'shadow_calibration_runs'

    id = Column(String, primary_key=True)
    suite_id = Column(String, ForeignKey('shadow_calibration_suites.id'), nullable=False, unique=True, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    release_id = Column(String, ForeignKey('releases.id'), nullable=False)
    report = Column(JSONType, nullable=False)
    report_sha256 = Column(String, nullable=False)
    executed_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DBShadowCalibrationFinding(Base):
    """A mismatch that requires a named institutional interpretation."""
    __tablename__ = 'shadow_calibration_findings'
    __table_args__ = (
        UniqueConstraint('run_id', 'case_id', name='uq_shadow_calibration_finding_case'),
        CheckConstraint("status IN ('OPEN', 'RESOLVED')", name='ck_shadow_calibration_finding_status'),
        CheckConstraint(
            "classification IN ('SOURCE_DATA', 'POLICY_MODEL', 'EVIDENCE', 'GOVERNANCE') OR classification IS NULL",
            name='ck_shadow_calibration_finding_classification',
        ),
    )

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey('shadow_calibration_runs.id'), nullable=False, index=True)
    case_id = Column(String, ForeignKey('shadow_calibration_cases.id'), nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    expected_decision = Column(String, nullable=False)
    actual_decision = Column(String, nullable=False)
    input_sha256 = Column(String, nullable=False)
    trace_sha256 = Column(String, nullable=False)
    status = Column(String, nullable=False, default="OPEN", index=True)
    classification = Column(String, nullable=True)
    resolution_note = Column(Text, nullable=True)
    resolved_by = Column(String, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DBRelease(Base):
    __tablename__ = 'releases'
    __table_args__ = (
        UniqueConstraint('domain_id', 'version', name='uq_release_domain_version'),
    )
    id = Column(String, primary_key=True)
    domain_id = Column(String, ForeignKey('domains.id'), nullable=False)
    version = Column(String, nullable=False)
    rule_graph_id = Column(String, nullable=False)
    digital_signature = Column(String, nullable=False)
    signed_payload = Column(JSONType, nullable=True)
    signed_payload_hash = Column(String, nullable=True)
    signing_key_id = Column(String, nullable=True)
    signing_public_key = Column(Text, nullable=True)
    # Nullable only for releases created before applicability controls existed.
    effective_from = Column(Date, nullable=True)
    effective_until = Column(Date, nullable=True)
    applicability = Column(JSONType, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DBRuleGraph(Base):
    __tablename__ = 'rule_graphs'
    id = Column(String, primary_key=True)
    release_id = Column(String, ForeignKey('releases.id'), nullable=False)
    compiled_bytecode = Column(JSONType, nullable=False, comment="The static ExpressionTree JSON")
    compiled_at = Column(DateTime(timezone=True), server_default=func.now())

class DBEvidence(Base):
    __tablename__ = 'evidence'
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    subject_id = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    cryptographic_hash = Column(String, nullable=False)
    # The actual blob might be stored in S3, with just the key here
    s3_key_reference = Column(String, nullable=True) 
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class DBClaim(Base):
    """An extracted assertion retained with its evidence and evaluation context."""
    __tablename__ = 'claims'
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    evidence_id = Column(String, ForeignKey('evidence.id'), nullable=False, index=True)
    reasoning_graph_id = Column(String, ForeignKey('reasoning_graphs.id'), nullable=False, index=True)
    target_path = Column(String, nullable=False)
    asserted_value = Column(JSONType, nullable=False)
    extraction_confidence = Column(Float, nullable=False)
    source_trust_level = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    source_quote = Column(Text, nullable=True)
    source_locator = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DBFact(Base):
    """An accepted fact retained with the complete claim-resolution outcome."""
    __tablename__ = 'facts'
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    reasoning_graph_id = Column(String, ForeignKey('reasoning_graphs.id'), nullable=False, index=True)
    target_path = Column(String, nullable=False)
    resolved_value = Column(JSONType, nullable=True)
    final_confidence = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    supporting_claim_ids = Column(JSONType, nullable=False)
    rejected_claim_ids = Column(JSONType, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DBSupportRequest(Base):
    """A request for human assistance that never becomes evaluation evidence."""
    __tablename__ = 'support_requests'
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    category = Column(String, nullable=False)
    contact_details = Column(Text, nullable=True)
    message = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="OPEN")
    response_due_at = Column(DateTime(timezone=True), nullable=True, index=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    retention_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DBSupportRequestEvent(Base):
    """Append-only status history for a human-assistance request."""
    __tablename__ = 'support_request_events'
    __table_args__ = (
        UniqueConstraint('support_request_id', 'sequence', name='uq_support_request_event_sequence'),
    )
    id = Column(String, primary_key=True)
    support_request_id = Column(String, ForeignKey('support_requests.id'), nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    actor_id = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DBDecisionReviewCase(Base):
    """A subject-initiated review of an immutable decision trace."""
    __tablename__ = 'decision_review_cases'

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    subject_id = Column(String, nullable=False, index=True)
    reasoning_graph_id = Column(String, ForeignKey('reasoning_graphs.id'), nullable=False, index=True)
    category = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    disputed_fact_paths = Column(JSONType, nullable=False)
    submitted_evidence_ids = Column(JSONType, nullable=False)
    status = Column(String, nullable=False, default="SUBMITTED")
    resolution = Column(String, nullable=True)
    response_message = Column(Text, nullable=True)
    response_due_at = Column(DateTime(timezone=True), nullable=True, index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String, nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    retention_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DBDecisionReviewCaseEvent(Base):
    """Append-only case history; it never rewrites the original decision."""
    __tablename__ = 'decision_review_case_events'
    __table_args__ = (
        UniqueConstraint('review_case_id', 'sequence', name='uq_decision_review_case_event_sequence'),
    )

    id = Column(String, primary_key=True)
    review_case_id = Column(String, ForeignKey('decision_review_cases.id'), nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    event_type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    resolution = Column(String, nullable=True)
    response_message = Column(Text, nullable=True)
    actor_id = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DBReasoningGraph(Base):
    """
    Stores the final dynamic ReasoningGraph as JSON/JSONB.
    In Postgres, this allows deep querying over nodes and edges via JSONB operators.
    """
    __tablename__ = 'reasoning_graphs'
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    subject_id = Column(String, nullable=False)
    rule_graph_id = Column(String, ForeignKey('rule_graphs.id'), nullable=False)
    release_id = Column(String, ForeignKey('releases.id'), nullable=True)
    evidence_id = Column(String, ForeignKey('evidence.id'), nullable=True)
    
    # We store the graph as a JSONB blob in Postgres to avoid thousands of row inserts per evaluation
    graph_data = Column(JSONType, nullable=False)
    
    # Flattened summary fields for fast indexing/querying
    overall_decision = Column(String, nullable=False)
    overall_confidence = Column(Float, nullable=False)
    evaluated_at = Column(DateTime(timezone=True), server_default=func.now())
