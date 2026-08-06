"""
Database Schema Definition.

Proves the transition from the filesystem to a relational database.
Maps the Core Domain Models into SQLAlchemy ORM tables for Postgres.
"""

from typing import Any

from sqlalchemy import CheckConstraint, Column, String, Float, Integer, Date, DateTime, ForeignKey, Index, Text, UniqueConstraint, text
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


class DBProviderTenantControl(Base):
    """Provider-owned operational metadata; it contains no student or policy data."""
    __tablename__ = 'provider_tenant_controls'
    __table_args__ = (
        CheckConstraint("lifecycle_state IN ('PILOT', 'ACTIVE', 'SUSPENDED', 'DECOMMISSIONED')", name='ck_provider_tenant_lifecycle'),
    )
    tenant_id = Column(String, ForeignKey('tenants.id'), primary_key=True)
    lifecycle_state = Column(String, nullable=False, default='PILOT', index=True)
    service_tier = Column(String, nullable=False, default='pilot')
    integration_status = Column(String, nullable=False, default='NOT_CONFIGURED')
    integration_observed_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String, nullable=False)
    updated_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DBProviderSupportAccessRequest(Base):
    """A non-operative request for exceptional support access, never an access grant."""
    __tablename__ = 'provider_support_access_requests'
    __table_args__ = (
        CheckConstraint("status IN ('REQUESTED', 'APPROVED', 'REJECTED', 'CLOSED')", name='ck_provider_support_access_status'),
    )
    id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey('tenants.id'), nullable=False, index=True)
    requested_by = Column(String, nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String, nullable=False, default='REQUESTED', index=True)
    approved_by = Column(String, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
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
    approved_by = Column(String, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    released_as_release_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DBPolicyAmbiguity(Base):
    """A governed unresolved interpretation scoped to affected policy facts."""
    __tablename__ = 'policy_ambiguities'

    id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey('tenants.id'), nullable=False, index=True)
    domain_id = Column(String, ForeignKey('domains.id'), nullable=False, index=True)
    source_citation = Column(Text, nullable=False)
    question = Column(Text, nullable=False)
    interpretation_options = Column(JSONType, nullable=False)
    affected_target_paths = Column(JSONType, nullable=False, default=list)
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
    # Triage is advisory only. It helps route human attention and never makes
    # a page or a rule authoritative.
    extraction_kind = Column(String, nullable=False, default="SELECTABLE_TEXT")
    review_priority = Column(String, nullable=False, default="NORMAL")
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
    provider_model_version = Column(String, nullable=True)
    provider_response_hash = Column(String, nullable=True)
    source_page_hash = Column(String, nullable=False)
    proposed_text = Column(Text, nullable=False)
    proposed_text_hash = Column(String, nullable=False)
    proposed_blocks = Column(JSON, nullable=True)
    quality_signals = Column(JSON, nullable=True)
    review_priority = Column(String, nullable=False, default="NORMAL")
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
    source_id = Column(String, nullable=True, index=True)
    source_system = Column(String, nullable=False)
    contract = Column(JSONType, nullable=False)
    contract_sha256 = Column(String, nullable=False)
    author_id = Column(String, nullable=False)
    status = Column(String, nullable=False, default='PENDING', index=True)
    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DBInstitutionalDataSource(Base):
    """A reviewed declaration of what a named institutional source may mean."""
    __tablename__ = 'institutional_data_sources'
    __table_args__ = (
        CheckConstraint("source_kind IN ('SYSTEM_OF_RECORD', 'LEARNING_PLATFORM', 'DEPARTMENT_RECORD', 'COMMITTEE_REGISTER', 'MANUAL')", name='ck_institutional_data_source_kind'),
        CheckConstraint("authority_level IN ('AUTHORITATIVE', 'WORKING', 'REFERENCE')", name='ck_institutional_data_source_authority'),
        CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED', 'RETIRED')", name='ck_institutional_data_source_status'),
        CheckConstraint("connector_kind IN ('NONE', 'REST_API', 'SFTP_PULL', 'DATABASE_VIEW', 'VENDOR_API')", name='ck_institutional_data_source_connector_kind'),
        CheckConstraint("connector_status IN ('NOT_CONFIGURED', 'CONFIGURED', 'TEST_FAILED', 'APPROVED', 'PAUSED', 'RETIRED')", name='ck_institutional_data_source_connector_status'),
        CheckConstraint("expected_refresh_hours IS NULL OR expected_refresh_hours > 0", name='ck_institutional_data_source_refresh'),
        Index('ix_institutional_data_sources_tenant_domain', 'tenant_id', 'domain_id'),
    )
    id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey('tenants.id'), nullable=False, index=True)
    domain_id = Column(String, ForeignKey('domains.id'), nullable=False, index=True)
    display_name = Column(String, nullable=False)
    source_kind = Column(String, nullable=False)
    authority_level = Column(String, nullable=False)
    source_owner = Column(String, nullable=False)
    expected_refresh_hours = Column(Integer, nullable=True)
    source_reference = Column(String, nullable=True)
    connector_kind = Column(String, nullable=False, default="NONE")
    credential_reference = Column(String, nullable=True)
    endpoint_reference = Column(String, nullable=True)
    allowed_object = Column(String, nullable=True)
    connector_status = Column(String, nullable=False, default="NOT_CONFIGURED")
    connector_last_checked_at = Column(DateTime(timezone=True), nullable=True)
    author_id = Column(String, nullable=False)
    status = Column(String, nullable=False, default='PENDING')
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
    workflows = Column(JSONType, nullable=True)
    source_manifest_hash = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DBWorkflowOutbox(Base):
    """A signed-release workflow intent held until an approved dispatcher exists."""

    __tablename__ = 'workflow_outbox'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'idempotency_key', name='uq_workflow_outbox_idempotency'),
        CheckConstraint("status IN ('HELD', 'SHADOW_READY', 'CANCELLED')", name='ck_workflow_outbox_status'),
    )

    id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey('tenants.id'), nullable=False, index=True)
    domain_id = Column(String, ForeignKey('domains.id'), nullable=False, index=True)
    release_id = Column(String, ForeignKey('releases.id'), nullable=False, index=True)
    reasoning_graph_id = Column(String, ForeignKey('reasoning_graphs.id'), nullable=False, index=True)
    workflow_id = Column(String, nullable=False)
    action_type = Column(String, nullable=False)
    action_payload = Column(JSONType, nullable=False)
    idempotency_key = Column(String, nullable=False)
    status = Column(String, nullable=False, default='HELD', index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DBInstitutionalContextEvent(Base):
    """A governed record explaining how institutional history affects one subject."""

    __tablename__ = 'institutional_context_events'
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('CONCESSION', 'CURRICULUM_APPLICABILITY', 'ASSESSMENT_ACCOMMODATION', "
            "'APPEAL_OUTCOME', 'REGISTRATION_POSITION', 'PROGRESSION_POSITION', 'GRADUATION_POSITION', 'OTHER')",
            name='ck_institutional_context_event_type',
        ),
        CheckConstraint("visibility IN ('SUBJECT', 'STAFF_ONLY')", name='ck_institutional_context_visibility'),
        CheckConstraint("status IN ('SUBMITTED', 'CERTIFIED', 'REJECTED')", name='ck_institutional_context_status'),
        CheckConstraint(
            "effective_until IS NULL OR effective_until >= effective_from",
            name='ck_institutional_context_effective_period',
        ),
        CheckConstraint(
            "predecessor_relationship IN ('SUPERSEDES', 'REVOKES') OR predecessor_relationship IS NULL",
            name='ck_institutional_context_predecessor_relationship',
        ),
        CheckConstraint(
            "(predecessor_event_id IS NULL AND predecessor_relationship IS NULL) "
            "OR (predecessor_event_id IS NOT NULL AND predecessor_relationship IS NOT NULL)",
            name='ck_institutional_context_predecessor_pair',
        ),
    )

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, ForeignKey('domains.id'), nullable=False, index=True)
    subject_id = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    student_summary = Column(Text, nullable=False)
    institutional_effect = Column(Text, nullable=False)
    authority_name = Column(String, nullable=False)
    authority_reference = Column(String, nullable=False)
    source_reference = Column(Text, nullable=False)
    event_date = Column(Date, nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_until = Column(Date, nullable=True)
    visibility = Column(String, nullable=False, default="SUBJECT")
    policy_release_id = Column(String, ForeignKey('releases.id'), nullable=True, index=True)
    policy_citation = Column(Text, nullable=True)
    predecessor_event_id = Column(String, ForeignKey('institutional_context_events.id'), nullable=True, index=True)
    predecessor_relationship = Column(String, nullable=True)
    status = Column(String, nullable=False, default="SUBMITTED", index=True)
    input_sha256 = Column(String, nullable=False)
    recorded_by = Column(String, nullable=False)
    attested_by = Column(String, nullable=True)
    attestation_note = Column(Text, nullable=True)
    attested_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DBInstitutionalContextEventAttestation(Base):
    """Append-only evidence that an institutional context record was reviewed."""

    __tablename__ = 'institutional_context_event_attestations'
    __table_args__ = (
        UniqueConstraint('context_event_id', 'sequence', name='uq_institutional_context_attestation_sequence'),
        CheckConstraint("action IN ('SUBMITTED', 'CERTIFIED', 'REJECTED')", name='ck_institutional_context_attestation_action'),
    )

    id = Column(String, primary_key=True)
    context_event_id = Column(String, ForeignKey('institutional_context_events.id'), nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    action = Column(String, nullable=False)
    actor_id = Column(String, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DBRuleGraph(Base):
    __tablename__ = 'rule_graphs'
    id = Column(String, primary_key=True)
    release_id = Column(String, ForeignKey('releases.id'), nullable=False)
    compiled_bytecode = Column(JSONType, nullable=False, comment="The static ExpressionTree JSON")
    compiled_at = Column(DateTime(timezone=True), server_default=func.now())

class DBEvidence(Base):
    __tablename__ = 'evidence'
    __table_args__ = (
        UniqueConstraint(
            'tenant_id', 'domain_id', 'source_mapping_id', 'source_record_fingerprint',
            name='uq_evidence_source_record_fingerprint',
        ),
    )
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    subject_id = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    source_authority = Column(String, nullable=False, default="subject_submitted")
    record_state = Column(String, nullable=False, default="provisional")
    source_system = Column(String, nullable=True)
    source_record_version = Column(String, nullable=True)
    source_as_of = Column(DateTime(timezone=True), nullable=True)
    source_mapping_id = Column(String, nullable=True)
    source_record_fingerprint = Column(String, nullable=True)
    cryptographic_hash = Column(String, nullable=False)
    # The actual blob might be stored in S3, with just the key here
    s3_key_reference = Column(String, nullable=True) 
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    retention_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deletion_reason = Column(String, nullable=True)

class DBEvidenceDeletionEvent(Base):
    """Append-only record of evidence soft-deletion."""
    __tablename__ = 'evidence_deletion_events'
    __table_args__ = (
        UniqueConstraint('evidence_id', name='uq_evidence_deletion_event_evidence'),
    )
    id = Column(String, primary_key=True)
    evidence_id = Column(String, ForeignKey('evidence.id'), nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    actor_id = Column(String, nullable=False)
    reason = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class DBEvidenceFactProposal(Base):
    """A source-referenced fact awaiting independent acceptance or rejection."""

    __tablename__ = 'evidence_fact_proposals'
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'REJECTED')",
            name='ck_evidence_fact_proposal_status',
        ),
        CheckConstraint(
            'extraction_confidence >= 0 AND extraction_confidence <= 1',
            name='ck_evidence_fact_proposal_extraction_confidence',
        ),
        CheckConstraint(
            'source_trust_level >= 0 AND source_trust_level <= 1',
            name='ck_evidence_fact_proposal_source_trust',
        ),
        Index(
            'uq_evidence_fact_proposal_accepted_target',
            'evidence_id',
            'target_path',
            unique=True,
            postgresql_where=text("status = 'ACCEPTED'"),
            sqlite_where=text("status = 'ACCEPTED'"),
        ),
    )

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    evidence_id = Column(String, ForeignKey('evidence.id'), nullable=False, index=True)
    subject_id = Column(String, nullable=False, index=True)
    target_path = Column(String, nullable=False, index=True)
    asserted_value = Column(JSONType, nullable=True)
    source_quote = Column(Text, nullable=False)
    source_locator = Column(String, nullable=True)
    extraction_confidence = Column(Float, nullable=False)
    source_trust_level = Column(Float, nullable=False)
    proposal_origin = Column(String, nullable=False, default='MANUAL')
    evidence_sha256 = Column(String, nullable=False)
    input_sha256 = Column(String, nullable=False)
    proposed_by = Column(String, nullable=False)
    status = Column(String, nullable=False, default='PENDING', index=True)
    reviewed_by = Column(String, nullable=True)
    review_note = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DBEvidenceFactProposalEvent(Base):
    """Append-only lifecycle evidence for a reviewed evidence-fact proposal."""

    __tablename__ = 'evidence_fact_proposal_events'
    __table_args__ = (
        UniqueConstraint(
            'proposal_id', 'sequence', name='uq_evidence_fact_proposal_event_sequence',
        ),
        CheckConstraint(
            "action IN ('SUBMITTED', 'ACCEPTED', 'REJECTED')",
            name='ck_evidence_fact_proposal_event_action',
        ),
    )

    id = Column(String, primary_key=True)
    proposal_id = Column(String, ForeignKey('evidence_fact_proposals.id'), nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    action = Column(String, nullable=False)
    actor_id = Column(String, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


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
    retention_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deletion_reason = Column(String, nullable=True)
    superseded_by_fact_id = Column(String, ForeignKey('facts.id'), nullable=True, index=True)
    superseded_at = Column(DateTime(timezone=True), nullable=True)
    superseding_reason = Column(String, nullable=True)

class DBFactSupersessionEvent(Base):
    """Append-only record of a fact being superseded."""
    __tablename__ = 'fact_supersession_events'
    __table_args__ = (
        UniqueConstraint('old_fact_id', name='uq_fact_supersession_event_old_fact'),
    )
    id = Column(String, primary_key=True)
    old_fact_id = Column(String, ForeignKey('facts.id'), nullable=False, index=True)
    new_fact_id = Column(String, ForeignKey('facts.id'), nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    actor_id = Column(String, nullable=False)
    reason = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

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
    responsible_group = Column(String, nullable=True)
    fallback_group = Column(String, nullable=True)
    escalation_due_at = Column(DateTime(timezone=True), nullable=True, index=True)
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
    responsible_group = Column(String, nullable=True)
    fallback_group = Column(String, nullable=True)
    escalation_due_at = Column(DateTime(timezone=True), nullable=True, index=True)
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
    retention_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deletion_reason = Column(String, nullable=True)
    overall_decision = Column(String, nullable=False)
    overall_confidence = Column(Float, nullable=False)
    evaluated_at = Column(DateTime(timezone=True), server_default=func.now())

class DBReasoningGraphDeletionEvent(Base):
    """Append-only record of a reasoning graph soft-deletion."""
    __tablename__ = 'reasoning_graph_deletion_events'
    id = Column(String, primary_key=True)
    reasoning_graph_id = Column(String, ForeignKey('reasoning_graphs.id'), nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    domain_id = Column(String, nullable=False, index=True)
    actor_id = Column(String, nullable=False)
    reason = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
