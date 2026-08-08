"""
Asynchronous Repository Pattern for the Engine.

Replaces the synchronous, blocking file-I/O from the initial prototype.
Now strictly backed by SQLAlchemy ORM to run against Postgres/SQLite.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, List, cast
import hashlib
import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, func, text, exists
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from app.core.models import Claim, Evidence, Fact, GraphEdge, GraphNode, ReasoningGraph, Release, RuleGraph, WorkflowRule
from app.infrastructure.db import (
    DBClaim,
    DBBackgroundJob,
    DBFact,
    DBHandbookPage,
    DBHandbookOcrReview,
    DBHandbookOcrReviewEvent,
    DBHandbookUpload,
    DBHandbookUploadSession,
    DBMetadataQuickEdit,
    DBMetadataOverride,
    DBSystemRecordImportMapping,
    DBSystemRecordImportMappingEvent,
    DBInstitutionalDataSource,
    DBShadowCalibrationCase,
    DBShadowCalibrationFinding,
    DBShadowCalibrationRun,
    DBShadowCalibrationSuite,
    DBShadowCalibrationSuiteEvent,
    DBRelease,
    DBRuleGraph,
    DBReasoningGraph,
    DBReasoningGraphDeletionEvent,
    DBEvidence,
    DBEvidenceDeletionEvent,
    DBFactSupersessionEvent,
    DBPolicyDraft,
    DBPolicyAmbiguity,
    DBPolicyAmbiguityEvent,
    DBDomain,
    DBDecisionReviewCase,
    DBDecisionReviewCaseEvent,
    DBInstitutionalContextEvent,
    DBInstitutionalContextEventAttestation,
    DBEvidenceFactProposal,
    DBEvidenceFactProposalEvent,
    DBSupportRequest,
    DBSupportRequestEvent,
    DBTenant,
    DBProviderTenantControl,
    DBProviderSupportAccessRequest,
    DBWorkflowOutbox,
)
from app.core.compiler import build_expression_tree
from app.core.lineage import stable_information_reference
from app.services.access_controls import (
    decision_review_response_due_at,
    casework_routing,
    decision_review_retention_days,
    response_due_at,
    support_request_retention_days,
)
from app.services.background_job_signals import BackgroundJobSignalError, publish_background_job_signal


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PolicyDraft:
    """Plain data carrier for a fetched draft row -- not persisted directly."""

    id: str
    tenant_id: str
    domain_id: str
    policy_name: str
    author_id: str
    payload: dict[str, Any]
    status: str
    approved_by: str | None = None
    approved_at: datetime | None = None


@dataclass(frozen=True)
class StoredEvidence:
    evidence: Evidence
    tenant_id: str
    domain_id: str


@dataclass(frozen=True)
class StoredEvaluationArtifacts:
    graph: ReasoningGraph
    tenant_id: str
    domain_id: str
    subject_id: str
    release_id: str
    evidence_id: str
    overall_decision: str
    overall_confidence: float
    claims: list[Claim]
    facts: list[Fact]


class QuickEditConflictError(ValueError):
    """Raised when an editor submits against a stale metadata value."""


class ReleaseVersionConflictError(ValueError):
    """Raised when a domain already has an immutable release at a version."""


class ReleaseApplicabilityConflictError(ValueError):
    """Raised when two releases would govern the same policy context."""


class PolicyAmbiguityConflictError(ValueError):
    """Raised when an ambiguity is transitioned outside its governed lifecycle."""


class GovernancePublicationBusyError(ValueError):
    """Raised when another publisher owns the domain governance lock."""


class DraftReleaseConflictError(ValueError):
    """Raised when a draft changed state before its release transaction commits."""


class EvidenceFactProposalConflictError(ValueError):
    """Raised when a proposed evidence fact violates its governed lifecycle."""


async def acquire_domain_governance_lock(session: AsyncSession, domain_id: str) -> None:
    """Serialise governed changes for one domain on production Postgres.

    The lock is transaction-scoped, so it is released automatically on the
    release/ambiguity commit or rollback. SQLite is intentionally a local test
    backend; production readiness rejects it before serving traffic.
    """
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return
    acquired = await session.scalar(
        text("SELECT pg_try_advisory_xact_lock(hashtext(:domain_id))"),
        {"domain_id": domain_id},
    )
    if acquired is not True:
        raise GovernancePublicationBusyError(
            "Another governed change is being recorded for this domain. Retry after it completes."
        )


class InstitutionalInputConflictError(ValueError):
    """Raised when a no-code intake conflicts with existing tenant/domain state."""


class PublicPolicyUnavailableError(ValueError):
    """Raised when a domain has not enabled a public approved-policy guide."""


class DecisionReviewUnavailableError(ValueError):
    """Raised when a domain has not enabled decision review casework."""


class DecisionReviewConflictError(ValueError):
    """Raised when a review case is transitioned outside its permitted workflow."""


class HandbookUploadConflictError(ValueError):
    """Raised when a handbook job cannot be transitioned safely."""


class BackgroundJobConflictError(ValueError):
    """Raised when a durable worker attempts an invalid job transition."""


class SystemRecordImportMappingConflictError(ValueError):
    """Raised when a mapping review would violate its governance lifecycle."""


class ShadowCalibrationConflictError(ValueError):
    """Raised when a non-operative calibration workflow violates its lifecycle."""


class InstitutionalContextEventConflictError(ValueError):
    """Raised when an institutional-history record violates its governance lifecycle."""


def _domain_presentation(schema_definition: dict[str, Any]) -> dict[str, str]:
    presentation = schema_definition.get("presentation", {})
    presentation = presentation if isinstance(presentation, dict) else {}

    def _label(key: str, default: str) -> str:
        value = presentation.get(key)
        return value.strip() if isinstance(value, str) and value.strip() else default

    return {
        "governed_person_label": _label("governed_person_label", "person"),
        "position_collection_label": _label("position_collection_label", "current positions"),
    }


def _domain_fact_labels(schema_definition: dict[str, Any]) -> dict[str, str]:
    properties = schema_definition.get("properties", {})
    facts = properties.get("facts", {}) if isinstance(properties, dict) else {}
    fact_properties = facts.get("properties", {}) if isinstance(facts, dict) else {}
    if not isinstance(fact_properties, dict):
        return {}
    return {
        f"facts.{key}": str(value.get("title", key.replace("_", " ").title()))
        for key, value in fact_properties.items()
        if isinstance(value, dict)
    }


def _safe_source_reference(proposal: DBEvidenceFactProposal, evidence: DBEvidence) -> Optional[str]:
    locator = cast(Optional[str], proposal.source_locator)
    if locator:
        lowered = locator.lower()
        if not lowered.startswith("approved mapping ") and not lowered.startswith("proposal:"):
            return locator
    version = cast(Optional[str], evidence.source_record_version)
    return f"Record version {version}" if version else None


def _student_information_status(status: str, *, conflicting: bool) -> tuple[str, str, str]:
    if status == "ACCEPTED":
        return (
            "accepted",
            "Accepted information",
            "This information has passed the institution's evidence governance step and can be used in decision traces.",
        )
    if conflicting:
        return (
            "conflict",
            "Needs review",
            "Cacisa has more than one pending interpretation for this information. It should not be treated as settled until governance resolves it.",
        )
    return (
        "provisional",
        "Awaiting confirmation",
        "Cacisa has received or interpreted this information, but it has not yet been accepted for decision-time use.",
    )


class MetadataGovernanceRepository:
    """Persistence operations for domain-configured, low-risk metadata."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def apply_quick_edit(
        self,
        *,
        edit_id: str,
        tenant_id: str,
        domain_id: str,
        target_type: str,
        target_id: str,
        field_name: str,
        submitted_old_value: Optional[str],
        new_value: str,
        reason: str,
        source_reference: Optional[str],
        actor_id: str,
        actor_role: str,
    ) -> dict[str, Any]:
        result = await self.session.execute(
            select(DBMetadataOverride).where(
                DBMetadataOverride.tenant_id == tenant_id,
                DBMetadataOverride.domain_id == domain_id,
                DBMetadataOverride.target_type == target_type,
                DBMetadataOverride.target_id == target_id,
                DBMetadataOverride.field_name == field_name,
            )
        )
        override = result.scalars().first()
        current_value = cast(Optional[str], override.current_value) if override else None

        if current_value is not None and submitted_old_value is not None and submitted_old_value != current_value:
            raise QuickEditConflictError(
                f"Current value is {current_value!r}; submitted old value was {submitted_old_value!r}."
            )

        old_value = current_value if current_value is not None else submitted_old_value
        audit = DBMetadataQuickEdit(
            id=edit_id,
            tenant_id=tenant_id,
            domain_id=domain_id,
            target_type=target_type,
            target_id=target_id,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
            source_reference=source_reference,
            actor_id=actor_id,
            actor_role=actor_role,
        )
        self.session.add(audit)

        if override:
            setattr(override, "current_value", new_value)
            setattr(override, "updated_by", actor_id)
            setattr(override, "last_edit_id", edit_id)
        else:
            self.session.add(
                DBMetadataOverride(
                    id="meta_" + edit_id.removeprefix("qe_"),
                    tenant_id=tenant_id,
                    domain_id=domain_id,
                    target_type=target_type,
                    target_id=target_id,
                    field_name=field_name,
                    current_value=new_value,
                    updated_by=actor_id,
                    last_edit_id=edit_id,
                )
            )

        await self.session.commit()
        return {
            "change_id": edit_id,
            "status": "applied",
            "tenant_id": tenant_id,
            "domain_id": domain_id,
            "target_type": target_type,
            "target_id": target_id,
            "field": field_name,
            "old_value": old_value,
            "new_value": new_value,
            "reason": reason,
            "source_reference": source_reference,
            "applied_by": actor_id,
        }

    async def list_quick_edits(
        self,
        *,
        tenant_id: str,
        domain_id: Optional[str] = None,
        target_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        query = select(DBMetadataQuickEdit).where(DBMetadataQuickEdit.tenant_id == tenant_id)
        if domain_id:
            query = query.where(DBMetadataQuickEdit.domain_id == domain_id)
        if target_id:
            query = query.where(DBMetadataQuickEdit.target_id == target_id)
        query = query.order_by(DBMetadataQuickEdit.applied_at.desc()).limit(limit)

        result = await self.session.execute(query)
        rows = result.scalars().all()
        return [
            {
                "change_id": cast(str, row.id),
                "domain_id": cast(str, row.domain_id),
                "target_type": cast(str, row.target_type),
                "target_id": cast(str, row.target_id),
                "field": cast(str, row.field_name),
                "old_value": cast(Optional[str], row.old_value),
                "new_value": cast(str, row.new_value),
                "reason": cast(str, row.reason),
                "source_reference": cast(Optional[str], row.source_reference),
                "applied_by": cast(str, row.actor_id),
                "actor_role": cast(str, row.actor_role),
                "applied_at": row.applied_at.isoformat() if row.applied_at else None,
            }
            for row in rows
        ]


    async def list_metadata_overrides(
        self,
        *,
        tenant_id: str,
        domain_id: str,
        target_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        query = select(DBMetadataOverride).where(
            DBMetadataOverride.tenant_id == tenant_id,
            DBMetadataOverride.domain_id == domain_id,
        )
        if target_id:
            query = query.where(DBMetadataOverride.target_id == target_id)

        result = await self.session.execute(query)
        rows = result.scalars().all()
        return [
            {
                "domain_id": cast(str, row.domain_id),
                "target_type": cast(str, row.target_type),
                "target_id": cast(str, row.target_id),
                "field": cast(str, row.field_name),
                "current_value": cast(str, row.current_value),
                "updated_by": cast(str, row.updated_by),
                "last_edit_id": cast(str, row.last_edit_id),
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]


class ProviderOperationsRepository:
    """Provider control-plane metadata only; never queries tenant casework or records."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _tenant_payload(control: DBProviderTenantControl, tenant: DBTenant) -> dict[str, Any]:
        return {
            "tenant_id": cast(str, tenant.id),
            "tenant_name": cast(str, tenant.name),
            "lifecycle_state": cast(str, control.lifecycle_state),
            "service_tier": cast(str, control.service_tier),
            "integration_status": cast(str, control.integration_status),
            "integration_observed_at": control.integration_observed_at.isoformat() if control.integration_observed_at else None,
            "created_at": control.created_at.isoformat() if control.created_at else None,
            "updated_at": control.updated_at.isoformat() if control.updated_at else None,
        }

    async def list_tenants(self) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(DBProviderTenantControl, DBTenant)
            .join(DBTenant, DBTenant.id == DBProviderTenantControl.tenant_id)
            .order_by(DBTenant.name)
        )
        return [self._tenant_payload(control, tenant) for control, tenant in result.all()]

    async def provision_tenant(self, *, tenant_id: str, tenant_name: str, actor_id: str) -> dict[str, Any]:
        if await self.session.get(DBTenant, tenant_id) is not None:
            raise ValueError("Tenant identifier already exists.")
        tenant = DBTenant(id=tenant_id, name=tenant_name)
        control = DBProviderTenantControl(
            tenant_id=tenant_id,
            lifecycle_state="PILOT",
            service_tier="pilot",
            integration_status="NOT_CONFIGURED",
            created_by=actor_id,
            updated_by=actor_id,
        )
        self.session.add(tenant)
        self.session.add(control)
        try:
            await self.session.commit()
            await self.session.refresh(tenant)
            await self.session.refresh(control)
        except IntegrityError as exc:
            await self.session.rollback()
            raise ValueError("Tenant provisioning conflicted with an existing record.") from exc
        return self._tenant_payload(control, tenant)

    async def update_lifecycle(self, *, tenant_id: str, lifecycle_state: str, actor_id: str) -> dict[str, Any] | None:
        control = await self.session.get(DBProviderTenantControl, tenant_id)
        tenant = await self.session.get(DBTenant, tenant_id)
        if control is None or tenant is None:
            return None
        setattr(control, "lifecycle_state", lifecycle_state)
        setattr(control, "updated_by", actor_id)
        await self.session.commit()
        await self.session.refresh(control)
        return self._tenant_payload(control, tenant)

    async def request_support_access(self, *, tenant_id: str, actor_id: str, reason: str) -> dict[str, Any] | None:
        if await self.session.get(DBProviderTenantControl, tenant_id) is None:
            return None
        request = DBProviderSupportAccessRequest(
            id="provider_support_" + uuid.uuid4().hex,
            tenant_id=tenant_id,
            requested_by=actor_id,
            reason=reason,
            status="REQUESTED",
        )
        self.session.add(request)
        await self.session.commit()
        return {
            "request_id": cast(str, request.id),
            "tenant_id": tenant_id,
            "status": "REQUESTED",
            "created_at": request.created_at.isoformat() if request.created_at else None,
        }


class InstitutionalInputRepository:
    """Creates a tenant domain and its first policy draft in one transaction."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_domain_with_draft(
        self,
        *,
        tenant_id: str,
        institution_name: str,
        domain_id: str,
        domain_name: str,
        schema_definition: dict[str, Any],
        draft_id: str,
        policy_name: str,
        author_id: str,
        policy_payload: dict[str, Any],
    ) -> None:
        existing_domain = await self.session.get(DBDomain, domain_id)
        if existing_domain is not None:
            raise InstitutionalInputConflictError("Generated domain identifier already exists; please retry.")

        existing_tenant = await self.session.get(DBTenant, tenant_id)
        if existing_tenant is None:
            self.session.add(DBTenant(id=tenant_id, name=institution_name))

        self.session.add(
            DBDomain(
                id=domain_id,
                tenant_id=tenant_id,
                name=domain_name,
                schema_definition=schema_definition,
            )
        )
        self.session.add(
            DBPolicyDraft(
                id=draft_id,
                tenant_id=tenant_id,
                domain_id=domain_id,
                policy_name=policy_name,
                author_id=author_id,
                payload=policy_payload,
                status="PENDING",
                approved_by=None,
                approved_at=None,
            )
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise InstitutionalInputConflictError(
                "Institutional input could not be saved due to a concurrent change."
            ) from exc

    async def list_domains(
        self,
        *,
        tenant_id: str,
        domain_ids: Optional[List[str]] = None,
    ) -> list[dict[str, str]]:
        query = select(DBDomain).where(DBDomain.tenant_id == tenant_id)
        if domain_ids is not None:
            if not domain_ids:
                return []
            query = query.where(DBDomain.id.in_(domain_ids))
        result = await self.session.execute(query.order_by(DBDomain.name))
        return [
            {"domain_id": cast(str, domain.id), "domain_name": cast(str, domain.name)}
            for domain in result.scalars().all()
        ]

    async def list_domain_fact_fields(
        self,
        *,
        tenant_id: str,
        domain_id: str,
    ) -> list[dict[str, str]] | None:
        """Return labelled facts declared by the no-code domain intake schema."""

        result = await self.session.execute(
            select(DBDomain).where(
                DBDomain.id == domain_id,
                DBDomain.tenant_id == tenant_id,
            )
        )
        domain = result.scalar_one_or_none()
        if domain is None:
            return None
        schema = cast(dict[str, Any], domain.schema_definition)
        properties = schema.get("properties", {})
        facts = properties.get("facts", {}) if isinstance(properties, dict) else {}
        fact_properties = facts.get("properties", {}) if isinstance(facts, dict) else {}
        if not isinstance(fact_properties, dict):
            return []
        return [
            {
                "target_path": f"facts.{key}",
                "label": str(value.get("title", key)),
                "schema_type": str(value.get("type", "string")),
            }
            for key, value in sorted(fact_properties.items())
            if isinstance(value, dict)
        ]

    async def get_domain_schema(self, *, tenant_id: str, domain_id: str) -> dict[str, Any] | None:
        domain = (await self.session.execute(select(DBDomain).where(
            DBDomain.id == domain_id, DBDomain.tenant_id == tenant_id,
        ))).scalar_one_or_none()
        return cast(dict[str, Any], domain.schema_definition) if domain is not None else None


class InstitutionalDataSourceRepository:
    """Stores source declarations; source credentials and records never enter this registry."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _payload(row: DBInstitutionalDataSource) -> dict[str, Any]:
        return {
            "source_id": cast(str, row.id), "domain_id": cast(str, row.domain_id),
            "display_name": cast(str, row.display_name), "source_kind": cast(str, row.source_kind),
            "authority_level": cast(str, row.authority_level), "source_owner": cast(str, row.source_owner),
            "expected_refresh_hours": cast(Optional[int], row.expected_refresh_hours),
            "source_reference": cast(Optional[str], row.source_reference), "author_id": cast(str, row.author_id),
            "connector_kind": cast(str, row.connector_kind),
            "credential_reference": cast(Optional[str], row.credential_reference),
            "endpoint_reference": cast(Optional[str], row.endpoint_reference),
            "allowed_object": cast(Optional[str], row.allowed_object),
            "connector_status": cast(str, row.connector_status),
            "connector_last_checked_at": row.connector_last_checked_at.isoformat() if row.connector_last_checked_at else None,
            "status": cast(str, row.status), "reviewed_by": cast(Optional[str], row.reviewed_by),
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
            "review_note": cast(Optional[str], row.review_note),
        }

    async def create(self, *, source_id: str, tenant_id: str, domain_id: str, author_id: str, **values: Any) -> dict[str, Any]:
        row = DBInstitutionalDataSource(id=source_id, tenant_id=tenant_id, domain_id=domain_id, author_id=author_id, status="PENDING", **values)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return self._payload(row)

    async def list_for_domain(self, *, tenant_id: str, domain_id: str) -> list[dict[str, Any]]:
        result = await self.session.execute(select(DBInstitutionalDataSource).where(
            DBInstitutionalDataSource.tenant_id == tenant_id, DBInstitutionalDataSource.domain_id == domain_id,
        ).order_by(DBInstitutionalDataSource.created_at.desc(), DBInstitutionalDataSource.id))
        return [self._payload(row) for row in result.scalars().all()]

    async def get(self, *, source_id: str, tenant_id: str, domain_id: str) -> Optional[dict[str, Any]]:
        row = (await self.session.execute(select(DBInstitutionalDataSource).where(
            DBInstitutionalDataSource.id == source_id, DBInstitutionalDataSource.tenant_id == tenant_id,
            DBInstitutionalDataSource.domain_id == domain_id,
        ))).scalars().first()
        return self._payload(row) if row else None

    async def review(self, *, source_id: str, tenant_id: str, domain_id: str, reviewer_id: str, approved: bool, note: Optional[str]) -> Optional[dict[str, Any]]:
        row = (await self.session.execute(select(DBInstitutionalDataSource).where(
            DBInstitutionalDataSource.id == source_id, DBInstitutionalDataSource.tenant_id == tenant_id,
            DBInstitutionalDataSource.domain_id == domain_id,
        ).with_for_update())).scalars().first()
        if not row:
            return None
        if row.status != "PENDING":
            raise SystemRecordImportMappingConflictError("This source declaration has already been reviewed.")
        if row.author_id == reviewer_id:
            raise SystemRecordImportMappingConflictError("Separation of duties violation: the source author cannot review their own declaration.")
        if not approved and not note:
            raise SystemRecordImportMappingConflictError("A rejection reason is required.")
        setattr(row, "status", "APPROVED" if approved else "REJECTED")
        setattr(row, "reviewed_by", reviewer_id)
        setattr(row, "reviewed_at", datetime.now(timezone.utc))
        setattr(row, "review_note", note)
        await self.session.commit()
        await self.session.refresh(row)
        return self._payload(row)


class SystemRecordImportMappingRepository:
    """Stores reviewed mapping configuration, never the CSV or subject values."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _payload(record: DBSystemRecordImportMapping) -> dict[str, Any]:
        return {
            "mapping_id": cast(str, record.id),
            "domain_id": cast(str, record.domain_id),
            "mapping_name": cast(str, record.mapping_name),
            "source_id": cast(Optional[str], record.source_id),
            "source_system": cast(str, record.source_system),
            "contract": cast(dict[str, Any], record.contract),
            "contract_sha256": cast(str, record.contract_sha256),
            "status": cast(str, record.status),
            "author_id": cast(str, record.author_id),
            "reviewed_by": cast(Optional[str], record.reviewed_by),
            "reviewed_at": record.reviewed_at.isoformat() if record.reviewed_at else None,
            "review_note": cast(Optional[str], record.review_note),
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }

    async def create(
        self,
        *,
        mapping_id: str,
        tenant_id: str,
        domain_id: str,
        mapping_name: str,
        source_system: str,
        source_id: Optional[str] = None,
        contract: dict[str, Any],
        contract_sha256: str,
        author_id: str,
    ) -> dict[str, Any]:
        record = DBSystemRecordImportMapping(
            id=mapping_id,
            tenant_id=tenant_id,
            domain_id=domain_id,
            mapping_name=mapping_name,
            source_id=source_id,
            source_system=source_system,
            contract=contract,
            contract_sha256=contract_sha256,
            author_id=author_id,
            status="PENDING",
        )
        self.session.add(record)
        try:
            # PostgreSQL validates the event against the persisted mapping state.
            await self.session.flush()
            self.session.add(
                DBSystemRecordImportMappingEvent(
                    id="mapping_evt_" + uuid.uuid4().hex,
                    mapping_id=mapping_id,
                    tenant_id=tenant_id,
                    domain_id=domain_id,
                    sequence=1,
                    event_type="SUBMITTED",
                    actor_id=author_id,
                )
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise SystemRecordImportMappingConflictError(
                "The mapping could not be saved due to a concurrent change."
            ) from exc
        await self.session.refresh(record)
        return self._payload(record)

    async def list_for_domain(
        self,
        *,
        tenant_id: str,
        domain_id: str,
        status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        query = select(DBSystemRecordImportMapping).where(
            DBSystemRecordImportMapping.tenant_id == tenant_id,
            DBSystemRecordImportMapping.domain_id == domain_id,
        )
        if status is not None:
            query = query.where(DBSystemRecordImportMapping.status == status)
        result = await self.session.execute(
            query.order_by(DBSystemRecordImportMapping.created_at.desc(), DBSystemRecordImportMapping.id)
        )
        return [self._payload(record) for record in result.scalars().all()]

    async def get(
        self,
        *,
        mapping_id: str,
        tenant_id: str,
        domain_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        query = select(DBSystemRecordImportMapping).where(
            DBSystemRecordImportMapping.id == mapping_id,
            DBSystemRecordImportMapping.tenant_id == tenant_id,
        )
        if domain_id is not None:
            query = query.where(DBSystemRecordImportMapping.domain_id == domain_id)
        record = (await self.session.execute(query)).scalars().first()
        return self._payload(record) if record is not None else None

    async def list_events(
        self,
        *,
        mapping_id: str,
        tenant_id: str,
        domain_id: str,
    ) -> Optional[list[dict[str, Any]]]:
        mapping = await self.get(
            mapping_id=mapping_id,
            tenant_id=tenant_id,
            domain_id=domain_id,
        )
        if mapping is None:
            return None
        result = await self.session.execute(
            select(DBSystemRecordImportMappingEvent).where(
                DBSystemRecordImportMappingEvent.mapping_id == mapping_id,
                DBSystemRecordImportMappingEvent.tenant_id == tenant_id,
                DBSystemRecordImportMappingEvent.domain_id == domain_id,
            ).order_by(DBSystemRecordImportMappingEvent.sequence)
        )
        return [
            {
                "sequence": cast(int, event.sequence),
                "event_type": cast(str, event.event_type),
                "actor_id": cast(str, event.actor_id),
                "note": cast(Optional[str], event.note),
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }
            for event in result.scalars().all()
        ]

    async def review(
        self,
        *,
        mapping_id: str,
        tenant_id: str,
        domain_id: str,
        reviewer_id: str,
        approved: bool,
        note: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        result = await self.session.execute(
            select(DBSystemRecordImportMapping).where(
                DBSystemRecordImportMapping.id == mapping_id,
                DBSystemRecordImportMapping.tenant_id == tenant_id,
                DBSystemRecordImportMapping.domain_id == domain_id,
            ).with_for_update()
        )
        record = result.scalars().first()
        if record is None:
            return None
        if record.status != "PENDING":
            raise SystemRecordImportMappingConflictError("This mapping has already been reviewed.")
        if record.author_id == reviewer_id:
            raise SystemRecordImportMappingConflictError(
                "Separation of duties violation: the mapping author cannot review their own mapping."
            )
        if not approved and not note:
            raise SystemRecordImportMappingConflictError("A rejection reason is required.")

        next_sequence = (
            await self.session.execute(
                select(func.max(DBSystemRecordImportMappingEvent.sequence)).where(
                    DBSystemRecordImportMappingEvent.mapping_id == mapping_id
                )
            )
        ).scalar_one_or_none() or 0
        reviewed_at = datetime.now(timezone.utc)
        status = "APPROVED" if approved else "REJECTED"
        setattr(record, "status", status)
        setattr(record, "reviewed_by", reviewer_id)
        setattr(record, "reviewed_at", reviewed_at)
        setattr(record, "review_note", note)
        # Flush the terminal state before adding its lifecycle-checked audit event.
        await self.session.flush()
        self.session.add(
            DBSystemRecordImportMappingEvent(
                id="mapping_evt_" + uuid.uuid4().hex,
                mapping_id=mapping_id,
                tenant_id=tenant_id,
                domain_id=domain_id,
                sequence=next_sequence + 1,
                event_type=status,
                actor_id=reviewer_id,
                note=note,
            )
        )
        await self.session.commit()
        await self.session.refresh(record)
        return self._payload(record)


class ShadowCalibrationRepository:
    """Stores governed, non-operative comparisons against a signed release."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    @staticmethod
    def _canonical_sha256(value: Any) -> str:
        serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def _suite_payload(cls, row: DBShadowCalibrationSuite, release_version: str, case_count: int) -> dict[str, Any]:
        return {
            "suite_id": cast(str, row.id),
            "domain_id": cast(str, row.domain_id),
            "release_id": cast(str, row.release_id),
            "release_version": release_version,
            "name": cast(str, row.name),
            "description": cast(str, row.description),
            "data_basis": cast(str, row.data_basis),
            "privacy_approval_reference": cast(Optional[str], row.privacy_approval_reference),
            "policy_as_of_date": row.policy_as_of_date.isoformat(),
            "author_id": cast(str, row.author_id),
            "status": cast(str, row.status),
            "input_sha256": cast(str, row.input_sha256),
            "certified_by": cast(Optional[str], row.certified_by),
            "certification_note": cast(Optional[str], row.certification_note),
            "certified_at": row.certified_at.isoformat() if row.certified_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "case_count": case_count,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _case_payload(row: DBShadowCalibrationCase) -> dict[str, Any]:
        return {
            "case_id": cast(str, row.id),
            "case_reference": cast(str, row.case_reference),
            "description": cast(str, row.description),
            "recorded_decision": cast(str, row.recorded_decision),
            "recorded_outcome_reference": cast(str, row.recorded_outcome_reference),
            "facts": cast(list[dict[str, Any]], row.facts),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @classmethod
    def _run_payload(cls, row: DBShadowCalibrationRun) -> dict[str, Any]:
        return {
            "run_id": cast(str, row.id),
            "report": cast(dict[str, Any], row.report),
            "report_sha256": cast(str, row.report_sha256),
            "executed_by": cast(str, row.executed_by),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @classmethod
    def _finding_payload(cls, row: DBShadowCalibrationFinding, case_reference: str) -> dict[str, Any]:
        resolved_at = cls._as_utc(cast(Optional[datetime], row.resolved_at))
        return {
            "finding_id": cast(str, row.id),
            "case_id": cast(str, row.case_id),
            "case_reference": case_reference,
            "expected_decision": cast(str, row.expected_decision),
            "actual_decision": cast(str, row.actual_decision),
            "input_sha256": cast(str, row.input_sha256),
            "trace_sha256": cast(str, row.trace_sha256),
            "status": cast(str, row.status),
            "classification": cast(Optional[str], row.classification),
            "resolution_note": cast(Optional[str], row.resolution_note),
            "resolved_by": cast(Optional[str], row.resolved_by),
            "resolved_at": resolved_at.isoformat() if resolved_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    async def create_suite(
        self,
        *,
        suite_id: str,
        tenant_id: str,
        domain_id: str,
        release_id: str,
        name: str,
        description: str,
        data_basis: str,
        privacy_approval_reference: Optional[str],
        policy_as_of_date: date,
        author_id: str,
        cases: list[dict[str, Any]],
    ) -> dict[str, Any]:
        input_snapshot = {
            "release_id": release_id,
            "name": name,
            "description": description,
            "data_basis": data_basis,
            "privacy_approval_reference": privacy_approval_reference,
            "policy_as_of_date": policy_as_of_date.isoformat(),
            "cases": cases,
        }
        suite = DBShadowCalibrationSuite(
            id=suite_id,
            tenant_id=tenant_id,
            domain_id=domain_id,
            release_id=release_id,
            name=name,
            description=description,
            data_basis=data_basis,
            privacy_approval_reference=privacy_approval_reference,
            policy_as_of_date=policy_as_of_date,
            author_id=author_id,
            status="SUBMITTED",
            input_sha256=self._canonical_sha256(input_snapshot),
        )
        self.session.add(suite)
        for case in cases:
            self.session.add(
                DBShadowCalibrationCase(
                    id=case["id"],
                    suite_id=suite_id,
                    tenant_id=tenant_id,
                    domain_id=domain_id,
                    case_reference=case["case_reference"],
                    description=case["description"],
                    recorded_decision=case["recorded_decision"],
                    recorded_outcome_reference=case["recorded_outcome_reference"],
                    facts=case["facts"],
                )
            )
        self.session.add(
            DBShadowCalibrationSuiteEvent(
                id="calibration_event_" + uuid.uuid4().hex,
                suite_id=suite_id,
                tenant_id=tenant_id,
                domain_id=domain_id,
                sequence=1,
                event_type="SUBMITTED",
                actor_id=author_id,
                note="Submitted for independent calibration certification.",
            )
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ShadowCalibrationConflictError("The calibration suite could not be recorded.") from exc
        return self._suite_payload(suite, "", len(cases))

    async def list_suites(
        self,
        *,
        tenant_id: str,
        domain_id: str,
    ) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(DBShadowCalibrationSuite, DBRelease.version, func.count(DBShadowCalibrationCase.id))
            .join(DBRelease, DBRelease.id == DBShadowCalibrationSuite.release_id)
            .outerjoin(DBShadowCalibrationCase, DBShadowCalibrationCase.suite_id == DBShadowCalibrationSuite.id)
            .where(
                DBShadowCalibrationSuite.tenant_id == tenant_id,
                DBShadowCalibrationSuite.domain_id == domain_id,
            )
            .group_by(DBShadowCalibrationSuite.id, DBRelease.version)
            .order_by(DBShadowCalibrationSuite.created_at.desc(), DBShadowCalibrationSuite.id)
        )
        return [
            self._suite_payload(suite, cast(str, version), cast(int, case_count))
            for suite, version, case_count in result.all()
        ]

    async def get_suite(
        self,
        *,
        suite_id: str,
        tenant_id: str,
        domain_id: str,
    ) -> Optional[dict[str, Any]]:
        suite_result = await self.session.execute(
            select(DBShadowCalibrationSuite, DBRelease.version)
            .join(DBRelease, DBRelease.id == DBShadowCalibrationSuite.release_id)
            .where(
                DBShadowCalibrationSuite.id == suite_id,
                DBShadowCalibrationSuite.tenant_id == tenant_id,
                DBShadowCalibrationSuite.domain_id == domain_id,
            )
        )
        row = suite_result.first()
        if row is None:
            return None
        suite, release_version = row
        case_rows = (
            await self.session.execute(
                select(DBShadowCalibrationCase)
                .where(DBShadowCalibrationCase.suite_id == suite_id)
                .order_by(DBShadowCalibrationCase.case_reference)
            )
        ).scalars().all()
        event_rows = (
            await self.session.execute(
                select(DBShadowCalibrationSuiteEvent)
                .where(DBShadowCalibrationSuiteEvent.suite_id == suite_id)
                .order_by(DBShadowCalibrationSuiteEvent.sequence)
            )
        ).scalars().all()
        run_row = (
            await self.session.execute(
                select(DBShadowCalibrationRun).where(DBShadowCalibrationRun.suite_id == suite_id)
            )
        ).scalars().first()
        findings: list[dict[str, Any]] = []
        if run_row is not None:
            finding_rows = await self.session.execute(
                select(DBShadowCalibrationFinding, DBShadowCalibrationCase.case_reference)
                .join(DBShadowCalibrationCase, DBShadowCalibrationCase.id == DBShadowCalibrationFinding.case_id)
                .where(DBShadowCalibrationFinding.run_id == run_row.id)
                .order_by(DBShadowCalibrationFinding.created_at, DBShadowCalibrationFinding.id)
            )
            findings = [
                self._finding_payload(finding, cast(str, case_reference))
                for finding, case_reference in finding_rows.all()
            ]
        return {
            **self._suite_payload(suite, cast(str, release_version), len(case_rows)),
            "cases": [self._case_payload(case) for case in case_rows],
            "events": [
                {
                    "event_type": cast(str, event.event_type),
                    "actor_id": cast(str, event.actor_id),
                    "note": cast(Optional[str], event.note),
                    "created_at": event.created_at.isoformat() if event.created_at else None,
                }
                for event in event_rows
            ],
            "run": self._run_payload(run_row) if run_row else None,
            "findings": findings,
        }

    async def certification_input(
        self,
        *,
        suite_id: str,
        tenant_id: str,
        domain_id: str,
    ) -> Optional[dict[str, Any]]:
        detail = await self.get_suite(suite_id=suite_id, tenant_id=tenant_id, domain_id=domain_id)
        return detail

    async def certify_suite(
        self,
        *,
        suite_id: str,
        tenant_id: str,
        domain_id: str,
        actor_id: str,
        note: str,
    ) -> Optional[dict[str, Any]]:
        result = await self.session.execute(
            select(DBShadowCalibrationSuite)
            .where(
                DBShadowCalibrationSuite.id == suite_id,
                DBShadowCalibrationSuite.tenant_id == tenant_id,
                DBShadowCalibrationSuite.domain_id == domain_id,
            )
            .with_for_update()
        )
        suite = result.scalars().first()
        if suite is None:
            return None
        if suite.status != "SUBMITTED":
            raise ShadowCalibrationConflictError("Only a submitted calibration suite can be certified.")
        if suite.author_id == actor_id:
            raise ShadowCalibrationConflictError("The suite author cannot certify their own calibration inputs.")
        now = datetime.now(timezone.utc)
        setattr(suite, "status", "CERTIFIED")
        setattr(suite, "certified_by", actor_id)
        setattr(suite, "certification_note", note)
        setattr(suite, "certified_at", now)
        self.session.add(
            DBShadowCalibrationSuiteEvent(
                id="calibration_event_" + uuid.uuid4().hex,
                suite_id=suite_id,
                tenant_id=tenant_id,
                domain_id=domain_id,
                sequence=2,
                event_type="CERTIFIED",
                actor_id=actor_id,
                note=note,
            )
        )
        await self.session.commit()
        return await self.get_suite(suite_id=suite_id, tenant_id=tenant_id, domain_id=domain_id)

    async def record_run(
        self,
        *,
        suite_id: str,
        tenant_id: str,
        domain_id: str,
        actor_id: str,
        report: dict[str, Any],
    ) -> dict[str, Any]:
        result = await self.session.execute(
            select(DBShadowCalibrationSuite)
            .where(
                DBShadowCalibrationSuite.id == suite_id,
                DBShadowCalibrationSuite.tenant_id == tenant_id,
                DBShadowCalibrationSuite.domain_id == domain_id,
            )
            .with_for_update()
        )
        suite = result.scalars().first()
        if suite is None:
            raise ShadowCalibrationConflictError("Calibration suite was not found.")
        if suite.status != "CERTIFIED":
            raise ShadowCalibrationConflictError("Only a certified calibration suite can run in shadow mode.")
        existing_run = await self.session.scalar(
            select(DBShadowCalibrationRun.id).where(DBShadowCalibrationRun.suite_id == suite_id)
        )
        if existing_run is not None:
            raise ShadowCalibrationConflictError("This calibration suite already has an immutable run report.")

        cases = (
            await self.session.execute(
                select(DBShadowCalibrationCase).where(DBShadowCalibrationCase.suite_id == suite_id)
            )
        ).scalars().all()
        cases_by_id = {cast(str, case.id): case for case in cases}
        run_id = "calibration_run_" + uuid.uuid4().hex
        self.session.add(
            DBShadowCalibrationRun(
                id=run_id,
                suite_id=suite_id,
                tenant_id=tenant_id,
                domain_id=domain_id,
                release_id=suite.release_id,
                report=report,
                report_sha256=self._canonical_sha256(report),
                executed_by=actor_id,
            )
        )
        reported_cases = report.get("cases")
        if not isinstance(reported_cases, list):
            raise ShadowCalibrationConflictError("Calibration report did not contain case results.")
        reported_case_ids = [item.get("id") for item in reported_cases if isinstance(item, dict)]
        if (
            len(reported_cases) != len(cases_by_id)
            or len(reported_case_ids) != len(cases_by_id)
            or len(set(reported_case_ids)) != len(reported_case_ids)
            or set(reported_case_ids) != set(cases_by_id)
        ):
            raise ShadowCalibrationConflictError("Calibration report did not match its immutable case set.")
        for result_item in reported_cases:
            if not isinstance(result_item, dict):
                raise ShadowCalibrationConflictError("Calibration report contained an invalid case result.")
            case_id = result_item.get("id")
            case = cases_by_id.get(case_id) if isinstance(case_id, str) else None
            if case is None:
                raise ShadowCalibrationConflictError("Calibration report did not match its immutable case set.")
            if result_item.get("passed") is False:
                self.session.add(
                    DBShadowCalibrationFinding(
                        id="calibration_finding_" + uuid.uuid4().hex,
                        run_id=run_id,
                        case_id=case_id,
                        tenant_id=tenant_id,
                        domain_id=domain_id,
                        expected_decision=result_item["expected_decision"],
                        actual_decision=result_item["actual_decision"],
                        input_sha256=result_item["input_sha256"],
                        trace_sha256=result_item["trace_sha256"],
                        status="OPEN",
                    )
                )
        setattr(suite, "status", "COMPLETED")
        setattr(suite, "completed_at", datetime.now(timezone.utc))
        self.session.add(
            DBShadowCalibrationSuiteEvent(
                id="calibration_event_" + uuid.uuid4().hex,
                suite_id=suite_id,
                tenant_id=tenant_id,
                domain_id=domain_id,
                sequence=3,
                event_type="COMPLETED",
                actor_id=actor_id,
                note="Shadow calibration report recorded. It does not create an operative decision.",
            )
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ShadowCalibrationConflictError("The calibration run could not be recorded.") from exc
        run = await self.session.get(DBShadowCalibrationRun, run_id)
        if run is None:
            raise ShadowCalibrationConflictError("Calibration run was not available after recording.")
        return self._run_payload(run)

    async def resolve_finding(
        self,
        *,
        finding_id: str,
        tenant_id: str,
        domain_id: str,
        actor_id: str,
        classification: str,
        note: str,
    ) -> Optional[dict[str, Any]]:
        result = await self.session.execute(
            select(DBShadowCalibrationFinding, DBShadowCalibrationSuite, DBShadowCalibrationCase.case_reference)
            .join(DBShadowCalibrationRun, DBShadowCalibrationRun.id == DBShadowCalibrationFinding.run_id)
            .join(DBShadowCalibrationSuite, DBShadowCalibrationSuite.id == DBShadowCalibrationRun.suite_id)
            .join(DBShadowCalibrationCase, DBShadowCalibrationCase.id == DBShadowCalibrationFinding.case_id)
            .where(
                DBShadowCalibrationFinding.id == finding_id,
                DBShadowCalibrationFinding.tenant_id == tenant_id,
                DBShadowCalibrationFinding.domain_id == domain_id,
            )
            .with_for_update()
        )
        row = result.first()
        if row is None:
            return None
        finding, suite, case_reference = row
        if finding.status != "OPEN":
            raise ShadowCalibrationConflictError("Only an open calibration mismatch can be classified.")
        if suite.author_id == actor_id:
            raise ShadowCalibrationConflictError("The suite author cannot classify their own calibration mismatch.")
        setattr(finding, "status", "RESOLVED")
        setattr(finding, "classification", classification)
        setattr(finding, "resolution_note", note)
        setattr(finding, "resolved_by", actor_id)
        setattr(finding, "resolved_at", datetime.now(timezone.utc))
        await self.session.commit()
        return self._finding_payload(finding, cast(str, case_reference))


class InstitutionalContextEventRepository:
    """Stores certified, subject-scoped institutional history without changing policy."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _canonical_sha256(value: Any) -> str:
        serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    @classmethod
    def _payload(
        cls,
        row: DBInstitutionalContextEvent,
        *,
        release_version: str | None,
        timeline_state: str,
        include_internal: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "event_id": cast(str, row.id),
            "domain_id": cast(str, row.domain_id),
            "event_type": cast(str, row.event_type),
            "title": cast(str, row.title),
            "student_summary": cast(str, row.student_summary),
            "institutional_effect": cast(str, row.institutional_effect),
            "authority_name": cast(str, row.authority_name),
            "event_date": row.event_date.isoformat(),
            "effective_from": row.effective_from.isoformat(),
            "effective_until": row.effective_until.isoformat() if row.effective_until else None,
            "visibility": cast(str, row.visibility),
            "policy_release_id": cast(Optional[str], row.policy_release_id),
            "policy_release_version": release_version,
            "policy_citation": cast(Optional[str], row.policy_citation),
            "status": cast(str, row.status),
            "timeline_state": timeline_state,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        if include_internal:
            attested_at = cls._as_utc(cast(Optional[datetime], row.attested_at))
            payload.update({
                "subject_id": cast(str, row.subject_id),
                "authority_reference": cast(str, row.authority_reference),
                "source_reference": cast(str, row.source_reference),
                "predecessor_event_id": cast(Optional[str], row.predecessor_event_id),
                "predecessor_relationship": cast(Optional[str], row.predecessor_relationship),
                "input_sha256": cast(str, row.input_sha256),
                "recorded_by": cast(str, row.recorded_by),
                "attested_by": cast(Optional[str], row.attested_by),
                "attestation_note": cast(Optional[str], row.attestation_note),
                "attested_at": attested_at.isoformat() if attested_at else None,
            })
        return payload

    async def _certified_successor_relationships(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        domain_id: str | None,
    ) -> dict[str, str]:
        query = select(
            DBInstitutionalContextEvent.predecessor_event_id,
            DBInstitutionalContextEvent.predecessor_relationship,
        ).where(
            DBInstitutionalContextEvent.tenant_id == tenant_id,
            DBInstitutionalContextEvent.subject_id == subject_id,
            DBInstitutionalContextEvent.status == "CERTIFIED",
            DBInstitutionalContextEvent.predecessor_event_id.is_not(None),
        )
        if domain_id is not None:
            query = query.where(DBInstitutionalContextEvent.domain_id == domain_id)
        rows = (await self.session.execute(query)).all()
        return {
            cast(str, predecessor_id): cast(str, relationship)
            for predecessor_id, relationship in rows
            if predecessor_id and relationship
        }

    async def _predecessor_for_update(
        self,
        *,
        predecessor_event_id: str,
        tenant_id: str,
        domain_id: str,
        subject_id: str,
    ) -> DBInstitutionalContextEvent:
        result = await self.session.execute(
            select(DBInstitutionalContextEvent)
            .where(
                DBInstitutionalContextEvent.id == predecessor_event_id,
                DBInstitutionalContextEvent.tenant_id == tenant_id,
                DBInstitutionalContextEvent.domain_id == domain_id,
                DBInstitutionalContextEvent.subject_id == subject_id,
            )
            .with_for_update()
        )
        predecessor = result.scalars().first()
        if predecessor is None or predecessor.status != "CERTIFIED":
            raise InstitutionalContextEventConflictError(
                "A context event can affect only a certified earlier event for the same subject and domain."
            )
        existing_successor = await self.session.scalar(
            select(DBInstitutionalContextEvent.id).where(
                DBInstitutionalContextEvent.predecessor_event_id == predecessor_event_id,
                DBInstitutionalContextEvent.status == "CERTIFIED",
            )
        )
        if existing_successor is not None:
            raise InstitutionalContextEventConflictError(
                "The earlier context event already has a certified superseding or revoking record."
            )
        return predecessor

    async def create_event(
        self,
        *,
        event_id: str,
        tenant_id: str,
        domain_id: str,
        subject_id: str,
        event_type: str,
        title: str,
        student_summary: str,
        institutional_effect: str,
        authority_name: str,
        authority_reference: str,
        source_reference: str,
        event_date: date,
        effective_from: date,
        effective_until: date | None,
        visibility: str,
        policy_release_id: str | None,
        policy_citation: str | None,
        predecessor_event_id: str | None,
        predecessor_relationship: str | None,
        recorded_by: str,
    ) -> dict[str, Any]:
        if predecessor_event_id:
            await self._predecessor_for_update(
                predecessor_event_id=predecessor_event_id,
                tenant_id=tenant_id,
                domain_id=domain_id,
                subject_id=subject_id,
            )
        snapshot = {
            "domain_id": domain_id,
            "subject_id": subject_id,
            "event_type": event_type,
            "title": title,
            "student_summary": student_summary,
            "institutional_effect": institutional_effect,
            "authority_name": authority_name,
            "authority_reference": authority_reference,
            "source_reference": source_reference,
            "event_date": event_date.isoformat(),
            "effective_from": effective_from.isoformat(),
            "effective_until": effective_until.isoformat() if effective_until else None,
            "visibility": visibility,
            "policy_release_id": policy_release_id,
            "policy_citation": policy_citation,
            "predecessor_event_id": predecessor_event_id,
            "predecessor_relationship": predecessor_relationship,
        }
        event = DBInstitutionalContextEvent(
            id=event_id,
            tenant_id=tenant_id,
            domain_id=domain_id,
            subject_id=subject_id,
            event_type=event_type,
            title=title,
            student_summary=student_summary,
            institutional_effect=institutional_effect,
            authority_name=authority_name,
            authority_reference=authority_reference,
            source_reference=source_reference,
            event_date=event_date,
            effective_from=effective_from,
            effective_until=effective_until,
            visibility=visibility,
            policy_release_id=policy_release_id,
            policy_citation=policy_citation,
            predecessor_event_id=predecessor_event_id,
            predecessor_relationship=predecessor_relationship,
            status="SUBMITTED",
            input_sha256=self._canonical_sha256(snapshot),
            recorded_by=recorded_by,
        )
        self.session.add(event)
        self.session.add(
            DBInstitutionalContextEventAttestation(
                id="context_attestation_" + uuid.uuid4().hex,
                context_event_id=event_id,
                tenant_id=tenant_id,
                domain_id=domain_id,
                sequence=1,
                action="SUBMITTED",
                actor_id=recorded_by,
                note="Submitted for independent certification as a record of an existing institutional decision.",
            )
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise InstitutionalContextEventConflictError("The institutional context event could not be recorded.") from exc
        event_payload = await self.get_event(
            event_id=event_id,
            tenant_id=tenant_id,
            include_internal=True,
        )
        if event_payload is None:
            raise InstitutionalContextEventConflictError("The institutional context event was not available after submission.")
        return event_payload

    async def list_events(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        domain_id: str | None,
        subject_safe: bool,
    ) -> list[dict[str, Any]]:
        query = (
            select(DBInstitutionalContextEvent, DBRelease.version)
            .outerjoin(DBRelease, DBRelease.id == DBInstitutionalContextEvent.policy_release_id)
            .where(
                DBInstitutionalContextEvent.tenant_id == tenant_id,
                DBInstitutionalContextEvent.subject_id == subject_id,
            )
        )
        if domain_id is not None:
            query = query.where(DBInstitutionalContextEvent.domain_id == domain_id)
        if subject_safe:
            query = query.where(
                DBInstitutionalContextEvent.status == "CERTIFIED",
                DBInstitutionalContextEvent.visibility == "SUBJECT",
            )
        rows = (
            await self.session.execute(
                query.order_by(
                    DBInstitutionalContextEvent.effective_from.desc(),
                    DBInstitutionalContextEvent.event_date.desc(),
                    DBInstitutionalContextEvent.id,
                )
            )
        ).all()
        successor_relationships = await self._certified_successor_relationships(
            tenant_id=tenant_id,
            subject_id=subject_id,
            domain_id=domain_id,
        )
        today = date.today()
        payloads = []
        for event, release_version in rows:
            event_id = cast(str, event.id)
            if event.status != "CERTIFIED":
                timeline_state = cast(str, event.status)
            elif successor_relationships.get(event_id) == "SUPERSEDES":
                timeline_state = "SUPERSEDED"
            elif successor_relationships.get(event_id) == "REVOKES":
                timeline_state = "REVOKED"
            elif event.effective_until and event.effective_until < today:
                timeline_state = "EXPIRED"
            else:
                timeline_state = "ACTIVE"
            payloads.append(self._payload(
                event,
                release_version=cast(Optional[str], release_version),
                timeline_state=timeline_state,
                include_internal=not subject_safe,
            ))
        return payloads

    async def get_event(
        self,
        *,
        event_id: str,
        tenant_id: str,
        include_internal: bool,
    ) -> Optional[dict[str, Any]]:
        result = await self.session.execute(
            select(DBInstitutionalContextEvent, DBRelease.version)
            .outerjoin(DBRelease, DBRelease.id == DBInstitutionalContextEvent.policy_release_id)
            .where(
                DBInstitutionalContextEvent.id == event_id,
                DBInstitutionalContextEvent.tenant_id == tenant_id,
            )
        )
        row = result.first()
        if row is None:
            return None
        event, release_version = row
        successor_relationships = await self._certified_successor_relationships(
            tenant_id=tenant_id,
            subject_id=cast(str, event.subject_id),
            domain_id=cast(str, event.domain_id),
        )
        event_id_value = cast(str, event.id)
        if event.status != "CERTIFIED":
            timeline_state = cast(str, event.status)
        elif successor_relationships.get(event_id_value) == "SUPERSEDES":
            timeline_state = "SUPERSEDED"
        elif successor_relationships.get(event_id_value) == "REVOKES":
            timeline_state = "REVOKED"
        elif event.effective_until and event.effective_until < date.today():
            timeline_state = "EXPIRED"
        else:
            timeline_state = "ACTIVE"
        return self._payload(
            event,
            release_version=cast(Optional[str], release_version),
            timeline_state=timeline_state,
            include_internal=include_internal,
        )

    async def attest_event(
        self,
        *,
        event_id: str,
        tenant_id: str,
        domain_id: str,
        actor_id: str,
        action: str,
        note: str,
    ) -> Optional[dict[str, Any]]:
        result = await self.session.execute(
            select(DBInstitutionalContextEvent)
            .where(
                DBInstitutionalContextEvent.id == event_id,
                DBInstitutionalContextEvent.tenant_id == tenant_id,
                DBInstitutionalContextEvent.domain_id == domain_id,
            )
            .with_for_update()
        )
        event = result.scalars().first()
        if event is None:
            return None
        if event.status != "SUBMITTED":
            raise InstitutionalContextEventConflictError("Only a submitted institutional context event can be attested.")
        if event.recorded_by == actor_id:
            raise InstitutionalContextEventConflictError("The person who recorded an event cannot attest it.")
        if action == "CERTIFY" and event.predecessor_event_id:
            await self._predecessor_for_update(
                predecessor_event_id=cast(str, event.predecessor_event_id),
                tenant_id=tenant_id,
                domain_id=domain_id,
                subject_id=cast(str, event.subject_id),
            )
        now = datetime.now(timezone.utc)
        status = "CERTIFIED" if action == "CERTIFY" else "REJECTED"
        setattr(event, "status", status)
        setattr(event, "attested_by", actor_id)
        setattr(event, "attestation_note", note)
        setattr(event, "attested_at", now)
        try:
            # PostgreSQL validates the state transition before it accepts its
            # matching append-only attestation, so persist the lifecycle state first.
            await self.session.flush()
            self.session.add(
                DBInstitutionalContextEventAttestation(
                    id="context_attestation_" + uuid.uuid4().hex,
                    context_event_id=event_id,
                    tenant_id=tenant_id,
                    domain_id=domain_id,
                    sequence=2,
                    action=status,
                    actor_id=actor_id,
                    note=note,
                )
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise InstitutionalContextEventConflictError("The institutional context attestation could not be recorded.") from exc
        return await self.get_event(event_id=event_id, tenant_id=tenant_id, include_internal=True)


class BackgroundJobRepository:
    """Durable, tenant-scoped queue records for non-decision processing.

    Jobs carry identifiers only. Source documents, evidence, and policy payloads
    remain in their purpose-specific stores and are retrieved under the job's
    tenant scope by the worker.
    """

    _SUPPORTED_TYPES = frozenset({"HANDBOOK_TEXT_EXTRACTION", "HANDBOOK_OCR"})

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _summary(job: DBBackgroundJob) -> dict[str, Any]:
        return {
            "job_id": cast(str, job.id),
            "tenant_id": cast(str, job.tenant_id),
            "domain_id": cast(str, job.domain_id),
            "job_type": cast(str, job.job_type),
            "resource_id": cast(str, job.resource_id),
            "status": cast(str, job.status),
            "attempts": cast(int, job.attempts),
            "max_attempts": cast(int, job.max_attempts),
            "available_at": job.available_at.isoformat() if job.available_at else None,
            "lease_expires_at": job.lease_expires_at.isoformat() if job.lease_expires_at else None,
            "locked_by": cast(Optional[str], job.locked_by),
            "last_error": cast(Optional[str], job.last_error),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }

    async def enqueue(
        self,
        *,
        tenant_id: str,
        domain_id: str,
        job_type: str,
        resource_id: str,
        max_attempts: int = 3,
        deduplication_key: str | None = None,
    ) -> dict[str, Any]:
        if job_type not in self._SUPPORTED_TYPES:
            raise BackgroundJobConflictError("Unsupported durable job type.")
        if not resource_id:
            raise BackgroundJobConflictError("Durable job resource identifier cannot be blank.")
        if not 1 <= max_attempts <= 10:
            raise BackgroundJobConflictError("Durable job max_attempts must be between 1 and 10.")

        deduplication_key = deduplication_key or f"{job_type}:{resource_id}"
        existing_result = await self.session.execute(
            select(DBBackgroundJob)
            .where(
                DBBackgroundJob.tenant_id == tenant_id,
                DBBackgroundJob.deduplication_key == deduplication_key,
            )
            .with_for_update()
        )
        existing = existing_result.scalars().first()
        if existing is not None:
            summary = self._summary(existing)
            if summary["status"] == "QUEUED":
                try:
                    await publish_background_job_signal(summary)
                except BackgroundJobSignalError as exc:
                    logger.warning("Background job signal publish failed for existing job %s: %s", summary["job_id"], exc)
            return summary

        job = DBBackgroundJob(
            id=f"job_{uuid.uuid4().hex}",
            tenant_id=tenant_id,
            domain_id=domain_id,
            job_type=job_type,
            resource_id=resource_id,
            deduplication_key=deduplication_key,
            status="QUEUED",
            attempts=0,
            max_attempts=max_attempts,
            available_at=datetime.now(timezone.utc),
        )
        self.session.add(job)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            existing_result = await self.session.execute(
                select(DBBackgroundJob).where(
                    DBBackgroundJob.tenant_id == tenant_id,
                    DBBackgroundJob.deduplication_key == deduplication_key,
                )
            )
            existing = existing_result.scalars().first()
            if existing is not None:
                return self._summary(existing)
            raise BackgroundJobConflictError("The durable job could not be queued.") from exc
        summary = self._summary(job)
        try:
            await publish_background_job_signal(summary)
        except BackgroundJobSignalError as exc:
            logger.warning("Background job signal publish failed for job %s: %s", summary["job_id"], exc)
        return summary

    async def claim_next(
        self,
        *,
        tenant_id: str,
        worker_id: str,
        lease_seconds: int,
    ) -> Optional[DBBackgroundJob]:
        if not worker_id:
            raise BackgroundJobConflictError("Durable workers require a non-empty worker identifier.")
        if not 30 <= lease_seconds <= 86_400:
            raise BackgroundJobConflictError("Durable job lease_seconds must be between 30 and 86400.")

        while True:
            now = datetime.now(timezone.utc)
            result = await self.session.execute(
                select(DBBackgroundJob)
                .where(
                    DBBackgroundJob.tenant_id == tenant_id,
                    (
                        ((DBBackgroundJob.status == "QUEUED") & (DBBackgroundJob.available_at <= now))
                        | ((DBBackgroundJob.status == "RUNNING") & (DBBackgroundJob.lease_expires_at <= now))
                    ),
                )
                .order_by(DBBackgroundJob.available_at, DBBackgroundJob.created_at, DBBackgroundJob.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            job = result.scalars().first()
            if job is None:
                return None
            if cast(int, job.attempts) >= cast(int, job.max_attempts):
                setattr(job, "status", "DEAD_LETTER")
                setattr(job, "lease_expires_at", None)
                setattr(job, "locked_by", None)
                setattr(job, "completed_at", now)
                setattr(job, "last_error", "Worker lease expired after the maximum permitted attempts.")
                await self.session.commit()
                continue

            setattr(job, "status", "RUNNING")
            setattr(job, "attempts", cast(int, job.attempts) + 1)
            setattr(job, "locked_by", worker_id)
            setattr(job, "lease_expires_at", now + timedelta(seconds=lease_seconds))
            setattr(job, "last_error", None)
            await self.session.commit()
            await self.session.refresh(job)
            return job

    async def renew_lease(
        self,
        *,
        job_id: str,
        tenant_id: str,
        worker_id: str,
        lease_seconds: int,
    ) -> bool:
        job = await self.session.get(DBBackgroundJob, job_id, with_for_update=True)
        if (
            job is None
            or job.tenant_id != tenant_id
            or job.status != "RUNNING"
            or job.locked_by != worker_id
        ):
            return False
        setattr(job, "lease_expires_at", datetime.now(timezone.utc) + timedelta(seconds=lease_seconds))
        await self.session.commit()
        return True

    async def mark_succeeded(self, *, job_id: str, tenant_id: str, worker_id: str) -> None:
        job = await self.session.get(DBBackgroundJob, job_id, with_for_update=True)
        if (
            job is None
            or job.tenant_id != tenant_id
            or job.status != "RUNNING"
            or job.locked_by != worker_id
        ):
            raise BackgroundJobConflictError("Durable job completion requires the active worker lease.")
        now = datetime.now(timezone.utc)
        setattr(job, "status", "SUCCEEDED")
        setattr(job, "lease_expires_at", None)
        setattr(job, "locked_by", None)
        setattr(job, "completed_at", now)
        setattr(job, "last_error", None)
        await self.session.commit()

    async def mark_failed(
        self,
        *,
        job_id: str,
        tenant_id: str,
        worker_id: str,
        error_message: str,
        retry_delay_seconds: int | None = None,
    ) -> str:
        job = await self.session.get(DBBackgroundJob, job_id, with_for_update=True)
        if (
            job is None
            or job.tenant_id != tenant_id
            or job.status != "RUNNING"
            or job.locked_by != worker_id
        ):
            raise BackgroundJobConflictError("Durable job failure requires the active worker lease.")

        now = datetime.now(timezone.utc)
        message = error_message.strip()[:1000] or "Worker execution failed without a safe diagnostic message."
        setattr(job, "lease_expires_at", None)
        setattr(job, "locked_by", None)
        setattr(job, "last_error", message)
        if cast(int, job.attempts) >= cast(int, job.max_attempts):
            setattr(job, "status", "DEAD_LETTER")
            setattr(job, "completed_at", now)
            await self.session.commit()
            return "DEAD_LETTER"

        delay = retry_delay_seconds
        if delay is None:
            delay = min(60 * (2 ** max(cast(int, job.attempts) - 1, 0)), 3600)
        if delay < 0 or delay > 86_400:
            raise BackgroundJobConflictError("Durable job retry delay must be between 0 and 86400 seconds.")
        setattr(job, "status", "QUEUED")
        setattr(job, "available_at", now + timedelta(seconds=delay))
        await self.session.commit()
        return "QUEUED"

    async def list_jobs(
        self,
        *,
        tenant_id: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if status is not None and status not in {"QUEUED", "RUNNING", "SUCCEEDED", "DEAD_LETTER"}:
            raise BackgroundJobConflictError("Unsupported durable job status filter.")
        query = select(DBBackgroundJob).where(DBBackgroundJob.tenant_id == tenant_id)
        if status is not None:
            query = query.where(DBBackgroundJob.status == status)
        result = await self.session.execute(
            query.order_by(DBBackgroundJob.created_at.desc(), DBBackgroundJob.id).limit(limit)
        )
        return [self._summary(job) for job in result.scalars().all()]


class HandbookRepository:
    """Persistent job and page checkpoints for large handbook extraction."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _summary(upload: DBHandbookUpload) -> dict[str, Any]:
        return {
            "handbook_id": cast(str, upload.id),
            "domain_id": cast(str, upload.domain_id),
            "file_name": cast(str, upload.file_name),
            "file_size_bytes": cast(int, upload.file_size_bytes),
            "content_hash": cast(Optional[str], upload.content_hash),
            "status": cast(str, upload.status),
            "total_pages": cast(Optional[int], upload.total_pages),
            "processed_pages": cast(int, upload.processed_pages),
            "error_message": cast(Optional[str], upload.error_message),
            "created_at": upload.created_at.isoformat() if upload.created_at else None,
            "updated_at": upload.updated_at.isoformat() if upload.updated_at else None,
        }

    async def create_upload(
        self,
        *,
        handbook_id: str,
        tenant_id: str,
        domain_id: str,
        file_name: str,
        content_type: str,
        file_size_bytes: int,
        content_hash: Optional[str],
        storage_key: str,
        uploaded_by: str,
    ) -> dict[str, Any]:
        upload = DBHandbookUpload(
            id=handbook_id,
            tenant_id=tenant_id,
            domain_id=domain_id,
            file_name=file_name,
            content_type=content_type,
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            storage_key=storage_key,
            uploaded_by=uploaded_by,
            status="QUEUED",
        )
        self.session.add(upload)
        try:
            await BackgroundJobRepository(self.session).enqueue(
                tenant_id=tenant_id,
                domain_id=domain_id,
                job_type="HANDBOOK_TEXT_EXTRACTION",
                resource_id=handbook_id,
            )
        except (IntegrityError, BackgroundJobConflictError) as exc:
            await self.session.rollback()
            raise HandbookUploadConflictError("The handbook upload could not be recorded.") from exc
        return self._summary(upload)

    @staticmethod
    def _session_summary(upload_session: DBHandbookUploadSession) -> dict[str, Any]:
        return {
            "session_id": cast(str, upload_session.id),
            "domain_id": cast(str, upload_session.domain_id),
            "file_name": cast(str, upload_session.file_name),
            "file_size_bytes": cast(int, upload_session.file_size_bytes),
            "expires_at": upload_session.expires_at.isoformat() if upload_session.expires_at else None,
        }

    async def create_upload_session(
        self,
        *,
        session_id: str,
        tenant_id: str,
        domain_id: str,
        file_name: str,
        content_type: str,
        file_size_bytes: int,
        storage_key: str,
        uploaded_by: str,
        expires_at: datetime,
    ) -> dict[str, Any]:
        upload_session = DBHandbookUploadSession(
            id=session_id,
            tenant_id=tenant_id,
            domain_id=domain_id,
            file_name=file_name,
            content_type=content_type,
            file_size_bytes=file_size_bytes,
            storage_key=storage_key,
            uploaded_by=uploaded_by,
            status="PENDING",
            expires_at=expires_at,
        )
        self.session.add(upload_session)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HandbookUploadConflictError("The handbook upload session could not be recorded.") from exc
        return self._session_summary(upload_session)

    async def get_pending_upload_session(
        self,
        session_id: str,
        *,
        tenant_id: str,
    ) -> DBHandbookUploadSession:
        result = await self.session.execute(
            select(DBHandbookUploadSession)
            .where(
                DBHandbookUploadSession.id == session_id,
                DBHandbookUploadSession.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        upload_session = result.scalars().first()
        if upload_session is None:
            raise HandbookUploadConflictError("The handbook upload session was not found.")
        if upload_session.status != "PENDING":
            raise HandbookUploadConflictError("This handbook upload session has already been completed.")

        expires_at = cast(datetime, upload_session.expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            setattr(upload_session, "status", "EXPIRED")
            await self.session.commit()
            raise HandbookUploadConflictError("This handbook upload session has expired. Start a new upload.")
        return upload_session

    async def complete_upload_session(
        self,
        upload_session: DBHandbookUploadSession,
        *,
        handbook_id: str,
    ) -> dict[str, Any]:
        handbook = DBHandbookUpload(
            id=handbook_id,
            tenant_id=upload_session.tenant_id,
            domain_id=upload_session.domain_id,
            file_name=upload_session.file_name,
            content_type=upload_session.content_type,
            file_size_bytes=upload_session.file_size_bytes,
            content_hash=None,
            storage_key=upload_session.storage_key,
            uploaded_by=upload_session.uploaded_by,
            status="QUEUED",
        )
        self.session.add(handbook)
        setattr(upload_session, "status", "COMPLETED")
        setattr(upload_session, "completed_at", datetime.now(timezone.utc))
        try:
            await BackgroundJobRepository(self.session).enqueue(
                tenant_id=cast(str, upload_session.tenant_id),
                domain_id=cast(str, upload_session.domain_id),
                job_type="HANDBOOK_TEXT_EXTRACTION",
                resource_id=handbook_id,
            )
        except (IntegrityError, BackgroundJobConflictError) as exc:
            await self.session.rollback()
            raise HandbookUploadConflictError("The completed handbook upload could not be queued.") from exc
        return self._summary(handbook)

    async def record_verified_source(self, handbook_id: str, *, content_hash: str, storage_key: str) -> None:
        upload = await self.session.get(DBHandbookUpload, handbook_id)
        if upload is None:
            raise HandbookUploadConflictError("Handbook upload was not found.")
        setattr(upload, "content_hash", content_hash)
        setattr(upload, "storage_key", storage_key)
        await self.session.commit()

    async def list_uploads(
        self,
        *,
        tenant_id: str,
        domain_ids: Optional[List[str]] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        query = select(DBHandbookUpload).where(DBHandbookUpload.tenant_id == tenant_id)
        if domain_ids is not None:
            if not domain_ids:
                return []
            query = query.where(DBHandbookUpload.domain_id.in_(domain_ids))
        result = await self.session.execute(
            query.order_by(DBHandbookUpload.created_at.desc(), DBHandbookUpload.id).limit(limit)
        )
        return [self._summary(upload) for upload in result.scalars().all()]

    async def get_upload(self, handbook_id: str, *, tenant_id: str) -> Optional[DBHandbookUpload]:
        result = await self.session.execute(
            select(DBHandbookUpload).where(
                DBHandbookUpload.id == handbook_id,
                DBHandbookUpload.tenant_id == tenant_id,
            )
        )
        return result.scalars().first()

    async def list_page_excerpts(
        self,
        *,
        handbook_id: str,
        after_page: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(DBHandbookPage)
            .where(
                DBHandbookPage.handbook_id == handbook_id,
                DBHandbookPage.page_number > after_page,
            )
            .order_by(DBHandbookPage.page_number)
            .limit(limit + 1)
        )
        return [
            {
                "page_number": cast(int, page.page_number),
                "text_content": cast(str, page.text_content),
                "content_hash": cast(str, page.content_hash),
                "extraction_kind": cast(str, page.extraction_kind),
                "review_priority": cast(str, page.review_priority),
            }
            for page in result.scalars().all()
        ]

    @staticmethod
    def _ocr_review_summary(review: DBHandbookOcrReview) -> dict[str, Any]:
        return {
            "ocr_review_id": cast(str, review.id),
            "page_number": cast(int, review.page_number),
            "provider_name": cast(str, review.provider_name),
            "provider_reference": cast(Optional[str], review.provider_reference),
            "provider_model_version": cast(Optional[str], review.provider_model_version),
            "provider_response_hash": cast(Optional[str], review.provider_response_hash),
            "source_page_hash": cast(str, review.source_page_hash),
            "proposed_text": cast(str, review.proposed_text),
            "proposed_text_hash": cast(str, review.proposed_text_hash),
            "proposed_blocks": cast(Optional[list[dict[str, Any]]], review.proposed_blocks),
            "quality_signals": cast(Optional[dict[str, Any]], review.quality_signals),
            "review_priority": cast(str, review.review_priority),
            "status": cast(str, review.status),
            "reviewed_text": cast(Optional[str], review.reviewed_text),
            "reviewed_by": cast(Optional[str], review.reviewed_by),
            "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
        }

    async def queue_ocr(self, handbook_id: str, *, tenant_id: str) -> DBHandbookUpload:
        result = await self.session.execute(
            select(DBHandbookUpload)
            .where(
                DBHandbookUpload.id == handbook_id,
                DBHandbookUpload.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        upload = result.scalars().first()
        if upload is None:
            raise HandbookUploadConflictError("Handbook source was not found.")
        if upload.status != "NEEDS_MANUAL_REVIEW":
            raise HandbookUploadConflictError("Only handbook sources awaiting manual review can be sent for OCR.")
        setattr(upload, "status", "OCR_QUEUED")
        setattr(upload, "error_message", None)
        try:
            await BackgroundJobRepository(self.session).enqueue(
                tenant_id=tenant_id,
                domain_id=cast(str, upload.domain_id),
                job_type="HANDBOOK_OCR",
                resource_id=handbook_id,
                max_attempts=1,
                deduplication_key=f"HANDBOOK_OCR:{handbook_id}:{uuid.uuid4().hex}",
            )
        except (IntegrityError, BackgroundJobConflictError) as exc:
            await self.session.rollback()
            raise HandbookUploadConflictError("The handbook OCR request could not be queued.") from exc
        await self.session.refresh(upload)
        return upload

    async def claim_ocr_upload(self, handbook_id: str) -> Optional[DBHandbookUpload]:
        result = await self.session.execute(
            select(DBHandbookUpload).where(DBHandbookUpload.id == handbook_id).with_for_update()
        )
        upload = result.scalars().first()
        if upload is None or upload.status not in {"OCR_QUEUED", "OCR_EXTRACTING"}:
            return None
        setattr(upload, "status", "OCR_EXTRACTING")
        await self.session.commit()
        return upload

    async def list_blank_page_numbers(self, handbook_id: str) -> list[int]:
        result = await self.session.execute(
            select(DBHandbookPage.page_number)
            .where(
                DBHandbookPage.handbook_id == handbook_id,
                func.length(func.trim(DBHandbookPage.text_content)) == 0,
            )
            .order_by(DBHandbookPage.page_number)
        )
        return [int(page_number) for page_number in result.scalars().all()]

    async def save_ocr_candidate(
        self,
        *,
        handbook_id: str,
        tenant_id: str,
        page_number: int,
        provider_name: str,
        provider_reference: Optional[str],
        proposed_text: str,
        provider_model_version: Optional[str],
        provider_response_hash: str,
        source_page_hash: str,
        proposed_blocks: list[dict[str, object]],
        quality_signals: dict[str, object],
        review_priority: str,
        commit: bool = True,
    ) -> None:
        review_id = f"handbook_ocr_review_{handbook_id}_{page_number}"
        existing = await self.session.get(DBHandbookOcrReview, review_id)
        if existing is not None:
            raise HandbookUploadConflictError("OCR proposals already exist for this handbook source.")
        proposed_hash = hashlib.sha256(proposed_text.encode("utf-8")).hexdigest()
        review = DBHandbookOcrReview(
            id=review_id,
            tenant_id=tenant_id,
            handbook_id=handbook_id,
            page_number=page_number,
            provider_name=provider_name,
            provider_reference=provider_reference,
            provider_model_version=provider_model_version,
            provider_response_hash=provider_response_hash,
            source_page_hash=source_page_hash,
            proposed_text=proposed_text,
            proposed_text_hash=proposed_hash,
            proposed_blocks=proposed_blocks,
            quality_signals=quality_signals,
            review_priority=review_priority,
            status="PENDING_REVIEW",
        )
        self.session.add(review)
        self.session.add(
            DBHandbookOcrReviewEvent(
                id=f"handbook_ocr_event_{uuid.uuid4().hex}",
                ocr_review_id=review_id,
                action="PROPOSED",
                actor_id=f"ocr_provider:{provider_name}",
                text_hash=proposed_hash,
                sequence=1,
            )
        )
        if commit:
            await self.session.commit()

    async def mark_ocr_review_required(self, handbook_id: str) -> None:
        upload = await self.session.get(DBHandbookUpload, handbook_id)
        if upload is None:
            raise HandbookUploadConflictError("Handbook source was not found.")
        setattr(upload, "status", "OCR_REVIEW_REQUIRED")
        await self.session.commit()

    async def mark_ocr_failed(self, handbook_id: str, message: str) -> None:
        upload = await self.session.get(DBHandbookUpload, handbook_id)
        if upload is None:
            return
        setattr(upload, "status", "NEEDS_MANUAL_REVIEW")
        setattr(upload, "error_message", message[:1000])
        await self.session.commit()

    async def list_ocr_reviews(self, handbook_id: str) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(DBHandbookOcrReview)
            .where(DBHandbookOcrReview.handbook_id == handbook_id)
            .order_by(DBHandbookOcrReview.page_number)
        )
        return [self._ocr_review_summary(review) for review in result.scalars().all()]

    async def review_ocr_candidate(
        self,
        *,
        handbook_id: str,
        page_number: int,
        action: str,
        reviewed_text: Optional[str],
        reviewer_id: str,
    ) -> dict[str, Any]:
        review_id = f"handbook_ocr_review_{handbook_id}_{page_number}"
        result = await self.session.execute(
            select(DBHandbookOcrReview).where(DBHandbookOcrReview.id == review_id).with_for_update()
        )
        review = result.scalars().first()
        if review is None:
            raise HandbookUploadConflictError("OCR proposal was not found.")
        if review.status not in {"PENDING_REVIEW", "REJECTED"}:
            raise HandbookUploadConflictError("This OCR proposal has already been accepted or corrected.")

        final_text: Optional[str]
        if action == "ACCEPT":
            final_text = cast(str, review.proposed_text)
            next_status = "ACCEPTED"
        elif action == "CORRECT":
            final_text = reviewed_text.strip() if reviewed_text else ""
            if not final_text:
                raise HandbookUploadConflictError("Corrected OCR text cannot be blank.")
            next_status = "CORRECTED"
        elif action == "REJECT":
            final_text = None
            next_status = "REJECTED"
        else:
            raise HandbookUploadConflictError("Unsupported OCR review action.")

        setattr(review, "status", next_status)
        setattr(review, "reviewed_text", final_text)
        setattr(review, "reviewed_by", reviewer_id)
        setattr(review, "reviewed_at", datetime.now(timezone.utc))
        sequence_result = await self.session.execute(
            select(func.count()).select_from(DBHandbookOcrReviewEvent).where(
                DBHandbookOcrReviewEvent.ocr_review_id == review_id
            )
        )
        final_hash = hashlib.sha256(final_text.encode("utf-8")).hexdigest() if final_text else None
        self.session.add(
            DBHandbookOcrReviewEvent(
                id=f"handbook_ocr_event_{uuid.uuid4().hex}",
                ocr_review_id=review_id,
                action=next_status,
                actor_id=reviewer_id,
                text_hash=final_hash,
                sequence=int(sequence_result.scalar_one()) + 1,
            )
        )

        if final_text:
            page_id = f"handbook_page_{handbook_id}_{page_number}"
            page = await self.session.get(DBHandbookPage, page_id)
            if page is None:
                raise HandbookUploadConflictError("Handbook page was not found.")
            setattr(page, "text_content", final_text)
            setattr(page, "content_hash", final_hash)
            setattr(page, "extraction_kind", "OCR_REVIEWED")
            upload = await self.session.get(DBHandbookUpload, handbook_id)
            if upload is None:
                raise HandbookUploadConflictError("Handbook source was not found.")
            await self.session.flush()
            if await self.count_pages_without_text(handbook_id) == 0:
                setattr(upload, "status", "READY_FOR_REVIEW")
                setattr(upload, "error_message", None)

        await self.session.commit()
        return self._ocr_review_summary(review)

    async def claim_queued_upload(self, handbook_id: str) -> Optional[DBHandbookUpload]:
        result = await self.session.execute(
            select(DBHandbookUpload).where(DBHandbookUpload.id == handbook_id).with_for_update()
        )
        upload = result.scalars().first()
        # A failed extraction may be reclaimed only by its durable retry job;
        # page checkpoints make the retried work idempotent.
        if upload is None or upload.status not in {"QUEUED", "EXTRACTING", "FAILED"}:
            return None
        setattr(upload, "status", "EXTRACTING")
        setattr(upload, "error_message", None)
        await self.session.commit()
        return upload

    async def claim_next_queued_upload(self) -> Optional[DBHandbookUpload]:
        result = await self.session.execute(
            select(DBHandbookUpload)
            .where(DBHandbookUpload.status == "QUEUED")
            .order_by(DBHandbookUpload.created_at, DBHandbookUpload.id)
            .limit(1)
            .with_for_update()
        )
        upload = result.scalars().first()
        if upload is None:
            return None
        setattr(upload, "status", "EXTRACTING")
        await self.session.commit()
        return upload

    async def set_total_pages(self, handbook_id: str, total_pages: int) -> None:
        upload = await self.session.get(DBHandbookUpload, handbook_id)
        if upload is None:
            raise HandbookUploadConflictError("Handbook upload was not found.")
        setattr(upload, "total_pages", total_pages)
        await self.session.commit()

    async def save_page(
        self,
        *,
        handbook_id: str,
        page_number: int,
        text_content: str,
        content_hash: str,
        extraction_kind: str = "SELECTABLE_TEXT",
        review_priority: str = "NORMAL",
    ) -> None:
        page_id = f"handbook_page_{handbook_id}_{page_number}"
        page = await self.session.get(DBHandbookPage, page_id)
        if page is None:
            self.session.add(
                DBHandbookPage(
                    id=page_id,
                    handbook_id=handbook_id,
                    page_number=page_number,
                    text_content=text_content,
                    content_hash=content_hash,
                    extraction_kind=extraction_kind,
                    review_priority=review_priority,
                )
            )
        else:
            setattr(page, "text_content", text_content)
            setattr(page, "content_hash", content_hash)
            setattr(page, "extraction_kind", extraction_kind)
            setattr(page, "review_priority", review_priority)
        upload = await self.session.get(DBHandbookUpload, handbook_id)
        if upload is None:
            raise HandbookUploadConflictError("Handbook upload was not found.")
        setattr(upload, "processed_pages", max(cast(int, upload.processed_pages), page_number))
        await self.session.commit()

    async def mark_ready(self, handbook_id: str) -> None:
        upload = await self.session.get(DBHandbookUpload, handbook_id)
        if upload is None:
            raise HandbookUploadConflictError("Handbook upload was not found.")
        setattr(upload, "status", "READY_FOR_REVIEW")
        await self.session.commit()

    async def count_pages_without_text(self, handbook_id: str) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(DBHandbookPage)
            .where(
                DBHandbookPage.handbook_id == handbook_id,
                func.length(func.trim(DBHandbookPage.text_content)) == 0,
            )
        )
        return int(result.scalar_one())

    async def mark_needs_manual_review(self, handbook_id: str, message: str) -> None:
        upload = await self.session.get(DBHandbookUpload, handbook_id)
        if upload is None:
            raise HandbookUploadConflictError("Handbook upload was not found.")
        setattr(upload, "status", "NEEDS_MANUAL_REVIEW")
        setattr(upload, "error_message", message[:1000])
        await self.session.commit()

    async def mark_failed(self, handbook_id: str, error_message: str) -> None:
        upload = await self.session.get(DBHandbookUpload, handbook_id)
        if upload is None:
            return
        setattr(upload, "status", "FAILED")
        setattr(upload, "error_message", error_message[:1000])
        await self.session.commit()


class PublicAccessRepository:
    """Read-only approved-policy guides and separate human-assistance requests."""

    _OPERATOR_LABELS = {
        "==": "is exactly",
        "!=": "is not",
        ">=": "is at least",
        "<=": "is at most",
        ">": "is greater than",
        "<": "is less than",
        "includes": "contains",
    }

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    @classmethod
    def _support_request_payload(cls, row: DBSupportRequest) -> dict[str, Any]:
        due_at = cls._as_utc(cast(Optional[datetime], row.response_due_at))
        escalation_due_at = cls._as_utc(cast(Optional[datetime], row.escalation_due_at))
        return {
            "id": cast(str, row.id),
            "domain_id": cast(str, row.domain_id),
            "category": cast(str, row.category),
            "contact_details": cast(Optional[str], row.contact_details),
            "message": cast(str, row.message),
            "status": cast(str, row.status),
            "response_due_at": due_at.isoformat() if due_at else None,
            "responsible_group": cast(Optional[str], row.responsible_group),
            "fallback_group": cast(Optional[str], row.fallback_group),
            "escalation_due_at": escalation_due_at.isoformat() if escalation_due_at else None,
            "is_escalated": bool(escalation_due_at and row.status != "CLOSED" and escalation_due_at < datetime.now(timezone.utc)),
            "closed_at": row.closed_at.isoformat() if row.closed_at else None,
            "retention_expires_at": row.retention_expires_at.isoformat() if row.retention_expires_at else None,
            "is_overdue": bool(
                due_at and row.status != "CLOSED" and due_at < datetime.now(timezone.utc)
            ),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _access_settings(domain: DBDomain) -> dict[str, Any]:
        schema = cast(dict[str, Any], domain.schema_definition)
        access = schema.get("access", {})
        return cast(dict[str, Any], access) if isinstance(access, dict) else {}

    @staticmethod
    def _fact_labels(domain: DBDomain) -> dict[str, str]:
        schema = cast(dict[str, Any], domain.schema_definition)
        properties = schema.get("properties", {})
        facts = properties.get("facts", {}) if isinstance(properties, dict) else {}
        fact_properties = facts.get("properties", {}) if isinstance(facts, dict) else {}
        if not isinstance(fact_properties, dict):
            return {}
        return {
            f"facts.{key}": str(value.get("title", key))
            for key, value in fact_properties.items()
            if isinstance(value, dict)
        }

    def _guide_node(self, node: dict[str, Any], fact_labels: dict[str, str]) -> dict[str, Any]:
        operator = node.get("operator")
        if operator:
            mode = {"AND": "all", "OR": "any", "NOT": "not"}.get(str(operator), "group")
            children = node.get("children", [])
            return {
                "kind": "group",
                "label": node.get("label", "Policy conditions"),
                "mode": mode,
                "children": [self._guide_node(child, fact_labels) for child in children if isinstance(child, dict)],
            }
        target = str(node.get("target", ""))
        return {
            "kind": "rule",
            "label": node.get("label", "Policy condition"),
            "fact_label": fact_labels.get(target, "Required information"),
            "operator": self._OPERATOR_LABELS.get(str(node.get("condition", "")), "is assessed against"),
            "expected_value": node.get("value"),
            "citation": node.get("source_citation"),
        }

    async def _approved_release(self, domain_id: str, version: Optional[str] = None) -> tuple[DBDomain, DBRelease, DBRuleGraph]:
        domain = await self.session.get(DBDomain, domain_id)
        if domain is None or not self._access_settings(domain).get("public_policy_guide", False):
            raise PublicPolicyUnavailableError("This policy guide is not publicly available.")

        query = select(DBRelease).where(DBRelease.domain_id == domain_id)
        if version:
            query = query.where(DBRelease.version == version)
        query = query.order_by(DBRelease.created_at.desc(), DBRelease.id.desc()).limit(1)
        release = (await self.session.execute(query)).scalars().first()
        if release is None:
            raise PublicPolicyUnavailableError("This policy has not been approved for public guidance yet.")
        graph = await self.session.get(DBRuleGraph, release.rule_graph_id)
        if graph is None:
            raise PublicPolicyUnavailableError("The approved policy could not be loaded.")
        return domain, release, graph

    async def list_public_policy_guides(self) -> list[dict[str, str]]:
        domains = (await self.session.execute(select(DBDomain).order_by(DBDomain.name))).scalars().all()
        guides: list[dict[str, str]] = []
        for domain in domains:
            if not self._access_settings(domain).get("public_policy_guide", False):
                continue
            release = (await self.session.execute(
                select(DBRelease)
                .where(DBRelease.domain_id == domain.id)
                .order_by(DBRelease.created_at.desc(), DBRelease.id.desc())
                .limit(1)
            )).scalars().first()
            if release:
                guides.append({
                    "domain_id": cast(str, domain.id),
                    "domain_name": cast(str, domain.name),
                    "version": cast(str, release.version),
                })
        return guides

    async def get_public_policy_guide(self, domain_id: str, version: Optional[str] = None) -> dict[str, Any]:
        domain, release, graph = await self._approved_release(domain_id, version)
        root = cast(dict[str, Any], graph.compiled_bytecode)
        schema = cast(dict[str, Any], domain.schema_definition)
        presentation = _domain_presentation(schema)
        return {
            "domain_id": cast(str, domain.id),
            "domain_name": cast(str, domain.name),
            "version": cast(str, release.version),
            "governed_person_label": presentation["governed_person_label"],
            "position_collection_label": presentation["position_collection_label"],
            "policy": self._guide_node(root, self._fact_labels(domain)),
            "assistance_requests_enabled": bool(self._access_settings(domain).get("assistance_requests_enabled", False)),
            "support_response_target_hours": self._access_settings(domain).get("support_response_target_hours"),
            "support_privacy_notice_url": self._access_settings(domain).get("support_privacy_notice_url"),
            "offline_assistance_instructions": self._access_settings(domain).get("offline_assistance_instructions"),
        }

    async def create_support_request(
        self,
        *,
        request_id: str,
        domain_id: str,
        category: str,
        contact_details: Optional[str],
        message: str,
    ) -> None:
        domain, _release, _graph = await self._approved_release(domain_id)
        if not self._access_settings(domain).get("assistance_requests_enabled", False):
            raise PublicPolicyUnavailableError("Human assistance requests are not enabled for this policy.")
        due_at = response_due_at(self._access_settings(domain))
        primary_group, fallback_group, escalation_due_at = casework_routing(cast(dict[str, object], domain.schema_definition))
        self.session.add(
            DBSupportRequest(
                id=request_id,
                tenant_id=domain.tenant_id,
                domain_id=domain_id,
                category=category,
                contact_details=contact_details,
                message=message,
                status="OPEN",
                response_due_at=due_at,
                responsible_group=primary_group,
                fallback_group=fallback_group,
                escalation_due_at=escalation_due_at,
            )
        )
        self.session.add(
            DBSupportRequestEvent(
                id="support_event_" + uuid.uuid4().hex,
                support_request_id=request_id,
                tenant_id=domain.tenant_id,
                domain_id=domain_id,
                sequence=1,
                status="OPEN",
                actor_id="public_submission",
            )
        )
        await self.session.commit()

    async def list_support_requests(
        self,
        *,
        tenant_id: str,
        domain_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(DBSupportRequest)
            .where(
                DBSupportRequest.tenant_id == tenant_id,
                DBSupportRequest.domain_id == domain_id,
            )
            .order_by(DBSupportRequest.created_at.desc(), DBSupportRequest.id)
            .limit(limit)
        )
        return [self._support_request_payload(row) for row in result.scalars().all()]

    async def update_support_request_status(
        self,
        *,
        request_id: str,
        tenant_id: str,
        domain_id: str,
        status: str,
        actor_id: str,
    ) -> Optional[dict[str, Any]]:
        result = await self.session.execute(
            select(DBSupportRequest).where(
                DBSupportRequest.id == request_id,
                DBSupportRequest.tenant_id == tenant_id,
                DBSupportRequest.domain_id == domain_id,
            ).with_for_update()
        )
        support_request = result.scalars().first()
        if support_request is None:
            return None
        if support_request.status != status:
            previous_status = support_request.status
            now = datetime.now(timezone.utc)
            latest_sequence = await self.session.scalar(
                select(func.max(DBSupportRequestEvent.sequence)).where(
                    DBSupportRequestEvent.support_request_id == request_id
                )
            )
            setattr(support_request, "status", status)
            if status == "CLOSED":
                setattr(support_request, "closed_at", now)
                setattr(
                    support_request,
                    "retention_expires_at",
                    now + timedelta(days=support_request_retention_days()),
                )
            elif previous_status == "CLOSED":
                domain = await self.session.get(DBDomain, domain_id)
                access_settings = self._access_settings(domain) if domain else {}
                setattr(support_request, "closed_at", None)
                setattr(support_request, "retention_expires_at", None)
                setattr(support_request, "response_due_at", response_due_at(access_settings))
            self.session.add(
                DBSupportRequestEvent(
                    id="support_event_" + uuid.uuid4().hex,
                    support_request_id=request_id,
                    tenant_id=tenant_id,
                    domain_id=domain_id,
                    sequence=(latest_sequence or 0) + 1,
                    status=status,
                    actor_id=actor_id,
                )
            )
        await self.session.commit()
        return self._support_request_payload(support_request)

    async def purge_expired_support_requests(self, *, now: datetime | None = None) -> int:
        """Deletes only closed requests whose configured retention period has elapsed."""
        current_time = now or datetime.now(timezone.utc)
        result = await self.session.execute(
            select(DBSupportRequest.id).where(
                DBSupportRequest.status == "CLOSED",
                DBSupportRequest.retention_expires_at.is_not(None),
                DBSupportRequest.retention_expires_at <= current_time,
            )
        )
        request_ids = list(result.scalars().all())
        if not request_ids:
            return 0
        await self.session.execute(
            delete(DBSupportRequestEvent).where(
                DBSupportRequestEvent.support_request_id.in_(request_ids)
            )
        )
        await self.session.execute(delete(DBSupportRequest).where(DBSupportRequest.id.in_(request_ids)))
        await self.session.commit()
        return len(request_ids)

    async def list_support_request_events(
        self,
        *,
        request_id: str,
        tenant_id: str,
        domain_id: str,
    ) -> Optional[list[dict[str, Any]]]:
        support_request = await self.session.get(DBSupportRequest, request_id)
        if (
            support_request is None
            or support_request.tenant_id != tenant_id
            or support_request.domain_id != domain_id
        ):
            return None
        result = await self.session.execute(
            select(DBSupportRequestEvent)
            .where(DBSupportRequestEvent.support_request_id == request_id)
            .order_by(DBSupportRequestEvent.sequence)
        )
        return [
            {
                "id": cast(str, event.id),
                "sequence": cast(int, event.sequence),
                "status": cast(str, event.status),
                "actor_id": cast(str, event.actor_id),
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }
            for event in result.scalars().all()
        ]


class DecisionReviewRepository:
    """Casework that lets a subject challenge a trace without rewriting it."""

    _ALLOWED_TRANSITIONS = {
        "SUBMITTED": {"ACKNOWLEDGED", "UNDER_REVIEW"},
        "ACKNOWLEDGED": {"UNDER_REVIEW"},
        "UNDER_REVIEW": {"RESOLVED"},
        "RESOLVED": {"CLOSED"},
        "CLOSED": set(),
    }

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    @staticmethod
    def _access_settings(domain: DBDomain) -> dict[str, Any]:
        schema = cast(dict[str, Any], domain.schema_definition)
        access = schema.get("access", {})
        return cast(dict[str, Any], access) if isinstance(access, dict) else {}

    @classmethod
    def _case_payload(cls, row: DBDecisionReviewCase) -> dict[str, Any]:
        due_at = cls._as_utc(cast(Optional[datetime], row.response_due_at))
        escalation_due_at = cls._as_utc(cast(Optional[datetime], row.escalation_due_at))
        return {
            "id": cast(str, row.id),
            "domain_id": cast(str, row.domain_id),
            "subject_id": cast(str, row.subject_id),
            "reasoning_graph_id": cast(str, row.reasoning_graph_id),
            "category": cast(str, row.category),
            "message": cast(str, row.message),
            "disputed_fact_paths": cast(list[str], row.disputed_fact_paths),
            "submitted_evidence_ids": cast(list[str], row.submitted_evidence_ids),
            "status": cast(str, row.status),
            "resolution": cast(Optional[str], row.resolution),
            "response_message": cast(Optional[str], row.response_message),
            "response_due_at": due_at.isoformat() if due_at else None,
            "responsible_group": cast(Optional[str], row.responsible_group),
            "fallback_group": cast(Optional[str], row.fallback_group),
            "escalation_due_at": escalation_due_at.isoformat() if escalation_due_at else None,
            "is_escalated": bool(escalation_due_at and row.status not in {"RESOLVED", "CLOSED"} and escalation_due_at < datetime.now(timezone.utc)),
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
            "closed_at": row.closed_at.isoformat() if row.closed_at else None,
            "retention_expires_at": row.retention_expires_at.isoformat() if row.retention_expires_at else None,
            "is_overdue": bool(
                due_at and row.status not in {"RESOLVED", "CLOSED"} and due_at < datetime.now(timezone.utc)
            ),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    async def create_case(
        self,
        *,
        case_id: str,
        tenant_id: str,
        domain_id: str,
        subject_id: str,
        reasoning_graph_id: str,
        category: str,
        message: str,
        disputed_fact_paths: list[str],
        submitted_evidence_ids: list[str],
        actor_id: str,
    ) -> dict[str, Any]:
        domain = await self.session.get(DBDomain, domain_id)
        if domain is None or domain.tenant_id != tenant_id:
            raise DecisionReviewUnavailableError("Decision review is not available for this domain.")
        access_settings = self._access_settings(domain)
        if not access_settings.get("decision_review_enabled", False):
            raise DecisionReviewUnavailableError("Decision review is not enabled for this domain.")
        due_at = decision_review_response_due_at(access_settings)
        if due_at is None:
            raise DecisionReviewUnavailableError("Decision review has no configured response commitment.")
        primary_group, fallback_group, escalation_due_at = casework_routing(cast(dict[str, object], domain.schema_definition))

        review_case = DBDecisionReviewCase(
            id=case_id,
            tenant_id=tenant_id,
            domain_id=domain_id,
            subject_id=subject_id,
            reasoning_graph_id=reasoning_graph_id,
            category=category,
            message=message,
            disputed_fact_paths=disputed_fact_paths,
            submitted_evidence_ids=submitted_evidence_ids,
            status="SUBMITTED",
            response_due_at=due_at,
            responsible_group=primary_group,
            fallback_group=fallback_group,
            escalation_due_at=escalation_due_at,
        )
        self.session.add(review_case)
        self.session.add(
            DBDecisionReviewCaseEvent(
                id="review_event_" + uuid.uuid4().hex,
                review_case_id=case_id,
                tenant_id=tenant_id,
                domain_id=domain_id,
                sequence=1,
                event_type="SUBMITTED",
                status="SUBMITTED",
                actor_id=actor_id,
            )
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise DecisionReviewConflictError("The decision review case could not be recorded.") from exc
        return self._case_payload(review_case)

    async def list_cases(
        self,
        *,
        tenant_id: str,
        domain_id: Optional[str],
        subject_id: Optional[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        query = select(DBDecisionReviewCase).where(DBDecisionReviewCase.tenant_id == tenant_id)
        if domain_id is not None:
            query = query.where(DBDecisionReviewCase.domain_id == domain_id)
        if subject_id is not None:
            query = query.where(DBDecisionReviewCase.subject_id == subject_id)
        result = await self.session.execute(
            query.order_by(DBDecisionReviewCase.created_at.desc(), DBDecisionReviewCase.id).limit(limit)
        )
        return [self._case_payload(row) for row in result.scalars().all()]

    async def get_case(self, case_id: str, *, tenant_id: str) -> Optional[dict[str, Any]]:
        result = await self.session.execute(
            select(DBDecisionReviewCase).where(
                DBDecisionReviewCase.id == case_id,
                DBDecisionReviewCase.tenant_id == tenant_id,
            )
        )
        review_case = result.scalars().first()
        return self._case_payload(review_case) if review_case else None

    async def update_case(
        self,
        *,
        case_id: str,
        tenant_id: str,
        domain_id: str,
        status: str,
        actor_id: str,
        resolution: Optional[str],
        response_message: Optional[str],
    ) -> Optional[dict[str, Any]]:
        result = await self.session.execute(
            select(DBDecisionReviewCase)
            .where(
                DBDecisionReviewCase.id == case_id,
                DBDecisionReviewCase.tenant_id == tenant_id,
                DBDecisionReviewCase.domain_id == domain_id,
            )
            .with_for_update()
        )
        review_case = result.scalars().first()
        if review_case is None:
            return None
        current_status = cast(str, review_case.status)
        if status not in self._ALLOWED_TRANSITIONS.get(current_status, set()):
            raise DecisionReviewConflictError(
                f"A review case cannot move from {current_status} to {status}."
            )
        if status == "RESOLVED":
            if not resolution or not response_message:
                raise DecisionReviewConflictError("Resolving a review case requires a resolution and a written response.")
        elif resolution is not None or response_message is not None:
            raise DecisionReviewConflictError("A resolution and written response may be recorded only when resolving a case.")

        now = datetime.now(timezone.utc)
        latest_sequence = await self.session.scalar(
            select(func.max(DBDecisionReviewCaseEvent.sequence)).where(
                DBDecisionReviewCaseEvent.review_case_id == case_id
            )
        )
        setattr(review_case, "status", status)
        event_type = "STATUS_CHANGED"
        if status == "RESOLVED":
            event_type = "RESOLVED"
            setattr(review_case, "resolution", resolution)
            setattr(review_case, "response_message", response_message)
            setattr(review_case, "resolved_at", now)
            setattr(review_case, "resolved_by", actor_id)
        elif status == "CLOSED":
            event_type = "CLOSED"
            setattr(review_case, "closed_at", now)
            setattr(
                review_case,
                "retention_expires_at",
                now + timedelta(days=decision_review_retention_days()),
            )

        self.session.add(
            DBDecisionReviewCaseEvent(
                id="review_event_" + uuid.uuid4().hex,
                review_case_id=case_id,
                tenant_id=tenant_id,
                domain_id=domain_id,
                sequence=(latest_sequence or 0) + 1,
                event_type=event_type,
                status=status,
                resolution=resolution if status == "RESOLVED" else None,
                response_message=response_message if status == "RESOLVED" else None,
                actor_id=actor_id,
            )
        )
        await self.session.commit()
        await self.session.refresh(review_case)
        return self._case_payload(review_case)

    async def list_case_events(
        self,
        *,
        case_id: str,
        tenant_id: str,
    ) -> Optional[list[dict[str, Any]]]:
        review_case = await self.get_case(case_id, tenant_id=tenant_id)
        if review_case is None:
            return None
        result = await self.session.execute(
            select(DBDecisionReviewCaseEvent)
            .where(
                DBDecisionReviewCaseEvent.review_case_id == case_id,
                DBDecisionReviewCaseEvent.tenant_id == tenant_id,
            )
            .order_by(DBDecisionReviewCaseEvent.sequence)
        )
        return [
            {
                "id": cast(str, event.id),
                "sequence": cast(int, event.sequence),
                "event_type": cast(str, event.event_type),
                "status": cast(str, event.status),
                "resolution": cast(Optional[str], event.resolution),
                "response_message": cast(Optional[str], event.response_message),
                "actor_id": cast(str, event.actor_id),
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }
            for event in result.scalars().all()
        ]

    async def purge_expired_cases(self, *, now: datetime | None = None) -> int:
        current_time = now or datetime.now(timezone.utc)
        result = await self.session.execute(
            select(DBDecisionReviewCase.id).where(
                DBDecisionReviewCase.status == "CLOSED",
                DBDecisionReviewCase.retention_expires_at.is_not(None),
                DBDecisionReviewCase.retention_expires_at <= current_time,
            )
        )
        case_ids = list(result.scalars().all())
        if not case_ids:
            return 0
        await self.session.execute(
            delete(DBDecisionReviewCaseEvent).where(
                DBDecisionReviewCaseEvent.review_case_id.in_(case_ids)
            )
        )
        await self.session.execute(delete(DBDecisionReviewCase).where(DBDecisionReviewCase.id.in_(case_ids)))
        await self.session.commit()
        return len(case_ids)


class PolicyAmbiguityRepository:
    """Persists unresolved interpretations as first-class governed records."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _payload(row: DBPolicyAmbiguity) -> dict[str, Any]:
        return {
            "ambiguity_id": cast(str, row.id),
            "tenant_id": cast(str, row.tenant_id),
            "domain_id": cast(str, row.domain_id),
            "source_citation": cast(str, row.source_citation),
            "question": cast(str, row.question),
            "interpretation_options": cast(list[str], row.interpretation_options),
            "affected_target_paths": cast(list[str], row.affected_target_paths or []),
            "status": cast(str, row.status),
            "resolution": cast(Optional[str], row.resolution),
            "resolution_source_reference": cast(Optional[str], row.resolution_source_reference),
            "resolved_by": cast(Optional[str], row.resolved_by),
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
            "created_by": cast(str, row.created_by),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    async def create(
        self,
        *,
        ambiguity_id: str,
        tenant_id: str,
        domain_id: str,
        source_citation: str,
        question: str,
        interpretation_options: list[str],
        affected_target_paths: list[str],
        created_by: str,
    ) -> dict[str, Any]:
        record = DBPolicyAmbiguity(
            id=ambiguity_id,
            tenant_id=tenant_id,
            domain_id=domain_id,
            source_citation=source_citation,
            question=question,
            interpretation_options=interpretation_options,
            affected_target_paths=affected_target_paths,
            status="OPEN",
            created_by=created_by,
        )
        self.session.add(record)
        self.session.add(
            DBPolicyAmbiguityEvent(
                id="amb_evt_" + uuid.uuid4().hex,
                ambiguity_id=ambiguity_id,
                tenant_id=tenant_id,
                domain_id=domain_id,
                sequence=1,
                event_type="RAISED",
                actor_id=created_by,
            )
        )
        await self.session.commit()
        await self.session.refresh(record)
        return self._payload(record)

    async def list_for_domain(
        self,
        *,
        tenant_id: str,
        domain_id: str,
        status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        query = select(DBPolicyAmbiguity).where(
            DBPolicyAmbiguity.tenant_id == tenant_id,
            DBPolicyAmbiguity.domain_id == domain_id,
        )
        if status is not None:
            query = query.where(DBPolicyAmbiguity.status == status)
        records = await self.session.execute(
            query.order_by(DBPolicyAmbiguity.created_at.desc(), DBPolicyAmbiguity.id)
        )
        return [self._payload(row) for row in records.scalars().all()]

    async def has_open_ambiguities(
        self,
        *,
        tenant_id: str,
        domain_id: str,
        affected_target_paths: set[str],
    ) -> bool:
        """Block only ambiguities that overlap the candidate release.

        Older records without a declared scope remain conservatively blocking
        until resolved. New records should name the fields they affect so an
        unrelated interpretation cannot freeze ordinary policy maintenance.
        """
        result = await self.session.execute(
            select(DBPolicyAmbiguity.affected_target_paths).where(
                DBPolicyAmbiguity.tenant_id == tenant_id,
                DBPolicyAmbiguity.domain_id == domain_id,
                DBPolicyAmbiguity.status == "OPEN",
            )
        )
        for paths in result.scalars().all():
            scoped_paths = set(cast(list[str], paths or []))
            if not scoped_paths or scoped_paths.intersection(affected_target_paths):
                return True
        return False

    async def resolve(
        self,
        *,
        ambiguity_id: str,
        tenant_id: str,
        domain_id: str,
        resolution: str,
        source_reference: str,
        actor_id: str,
    ) -> Optional[dict[str, Any]]:
        result = await self.session.execute(
            select(DBPolicyAmbiguity).where(
                DBPolicyAmbiguity.id == ambiguity_id,
                DBPolicyAmbiguity.tenant_id == tenant_id,
                DBPolicyAmbiguity.domain_id == domain_id,
            )
        )
        record = result.scalars().first()
        if record is None:
            return None
        if record.status != "OPEN":
            raise PolicyAmbiguityConflictError("This policy ambiguity has already been resolved.")
        if record.created_by == actor_id:
            raise PolicyAmbiguityConflictError(
                "Separation of duties violation: the person who raised an ambiguity cannot resolve it."
            )

        next_sequence = (
            await self.session.execute(
                select(func.max(DBPolicyAmbiguityEvent.sequence)).where(
                    DBPolicyAmbiguityEvent.ambiguity_id == ambiguity_id
                )
            )
        ).scalar_one_or_none() or 0
        resolved_at = datetime.now(timezone.utc)
        setattr(record, "status", "RESOLVED")
        setattr(record, "resolution", resolution)
        setattr(record, "resolution_source_reference", source_reference)
        setattr(record, "resolved_by", actor_id)
        setattr(record, "resolved_at", resolved_at)
        self.session.add(
            DBPolicyAmbiguityEvent(
                id="amb_evt_" + uuid.uuid4().hex,
                ambiguity_id=ambiguity_id,
                tenant_id=tenant_id,
                domain_id=domain_id,
                sequence=next_sequence + 1,
                event_type="RESOLVED",
                actor_id=actor_id,
                resolution=resolution,
                source_reference=source_reference,
            )
        )
        await self.session.commit()
        await self.session.refresh(record)
        return self._payload(record)


class DraftRepository:
    """
    Persists the governance gate: Draft -> Review -> Release.
    A draft is never edited in place -- it is created PENDING and then
    transitions exactly once, to RELEASED or REJECTED.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    _OPERATOR_LABELS = {
        "==": "is exactly",
        "!=": "is not",
        ">=": "is at least",
        "<=": "is at most",
        ">": "is greater than",
        "<": "is less than",
        "includes": "contains",
    }

    @staticmethod
    def _fact_labels(domain: DBDomain) -> dict[str, str]:
        schema = cast(dict[str, Any], domain.schema_definition)
        properties = schema.get("properties", {})
        facts = properties.get("facts", {}) if isinstance(properties, dict) else {}
        fact_properties = facts.get("properties", {}) if isinstance(facts, dict) else {}
        if not isinstance(fact_properties, dict):
            return {}
        return {
            f"facts.{key}": str(value.get("title", key))
            for key, value in fact_properties.items()
            if isinstance(value, dict)
        }

    @classmethod
    def _review_node(cls, node: dict[str, Any], fact_labels: dict[str, str]) -> dict[str, Any]:
        operator = node.get("operator")
        if operator:
            mode = {"AND": "all", "OR": "any", "NOT": "not"}.get(str(operator), "group")
            children = node.get("children", [])
            return {
                "kind": "group",
                "label": node.get("label", "Policy conditions"),
                "mode": mode,
                "children": [cls._review_node(child, fact_labels) for child in children if isinstance(child, dict)],
            }
        target = str(node.get("target", ""))
        return {
            "kind": "rule",
            "label": node.get("label", "Policy condition"),
            "fact_label": fact_labels.get(target, "Required information"),
            "operator": cls._OPERATOR_LABELS.get(str(node.get("condition", "")), "is assessed against"),
            "expected_value": node.get("value"),
            "citation": node.get("source_citation"),
        }

    async def list_pending_reviews(
        self,
        *,
        tenant_id: str,
        domain_ids: Optional[List[str]] = None,
    ) -> list[dict[str, Any]]:
        query = (
            select(DBPolicyDraft, DBDomain)
            .join(DBDomain, DBPolicyDraft.domain_id == DBDomain.id)
            .where(DBPolicyDraft.tenant_id == tenant_id, DBPolicyDraft.status == "PENDING")
        )
        if domain_ids is not None:
            if not domain_ids:
                return []
            query = query.where(DBPolicyDraft.domain_id.in_(domain_ids))
        rows = await self.session.execute(query.order_by(DBPolicyDraft.created_at, DBPolicyDraft.id))
        return [
            {
                "draft_id": cast(str, draft.id),
                "domain_id": cast(str, draft.domain_id),
                "domain_name": cast(str, domain.name),
                "policy_name": cast(str, draft.policy_name),
                "author_id": cast(str, draft.author_id),
                "created_at": draft.created_at.isoformat() if draft.created_at else None,
            }
            for draft, domain in rows.all()
        ]

    async def get_pending_review(
        self,
        *,
        draft_id: str,
        tenant_id: str,
    ) -> Optional[dict[str, Any]]:
        result = await self.session.execute(
            select(DBPolicyDraft, DBDomain)
            .join(DBDomain, DBPolicyDraft.domain_id == DBDomain.id)
            .where(
                DBPolicyDraft.id == draft_id,
                DBPolicyDraft.tenant_id == tenant_id,
                DBPolicyDraft.status == "PENDING",
            )
        )
        row = result.first()
        if row is None:
            return None
        draft, domain = row
        payload = cast(dict[str, Any], draft.payload)
        root = payload.get("root")
        if not isinstance(root, dict):
            return None
        return {
            "draft_id": cast(str, draft.id),
            "domain_id": cast(str, draft.domain_id),
            "domain_name": cast(str, domain.name),
            "policy_name": cast(str, draft.policy_name),
            "author_id": cast(str, draft.author_id),
            "created_at": draft.created_at.isoformat() if draft.created_at else None,
            "policy": self._review_node(root, self._fact_labels(domain)),
        }

    async def create_draft(self, draft_id: str, tenant_id: str, domain_id: str,
                            policy_name: str, author_id: str, payload: dict) -> str:
        db_draft = DBPolicyDraft(
            id=draft_id,
            tenant_id=tenant_id,
            domain_id=domain_id,
            policy_name=policy_name,
            author_id=author_id,
            payload=payload,
            status="PENDING",
            approved_by=None,
            approved_at=None,
        )
        self.session.add(db_draft)
        await self.session.commit()
        return cast(str, db_draft.id)

    async def get_draft(self, draft_id: str) -> Optional[PolicyDraft]:
        result = await self.session.execute(
            select(DBPolicyDraft).where(DBPolicyDraft.id == draft_id)
        )
        db_draft = result.scalars().first()
        if not db_draft:
            return None
        return PolicyDraft(
            id=cast(str, db_draft.id),
            tenant_id=cast(str, db_draft.tenant_id),
            domain_id=cast(str, db_draft.domain_id),
            policy_name=cast(str, db_draft.policy_name),
            author_id=cast(str, db_draft.author_id),
            payload=cast(dict[str, Any], db_draft.payload),
            status=cast(str, db_draft.status),
            approved_by=cast(Optional[str], db_draft.approved_by),
            approved_at=cast(Optional[datetime], db_draft.approved_at),
        )

    async def mark_released(
        self,
        draft_id: str,
        release_id: str,
        *,
        approved_by: str | None = None,
        approved_at: datetime | None = None,
    ) -> None:
        result = await self.session.execute(
            select(DBPolicyDraft).where(DBPolicyDraft.id == draft_id)
        )
        db_draft = result.scalars().first()
        if db_draft:
            setattr(db_draft, "status", "RELEASED")
            setattr(db_draft, "approved_by", approved_by)
            setattr(db_draft, "approved_at", approved_at or datetime.now(timezone.utc))
            setattr(db_draft, "released_as_release_id", release_id)
            await self.session.commit()

class EvidenceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
        
    async def create_evidence(
        self,
        evidence: Evidence,
        *,
        tenant_id: str,
        domain_id: str,
    ) -> None:
        self.session.add(
            DBEvidence(
                id=evidence.id,
                tenant_id=tenant_id,
                domain_id=domain_id,
                subject_id=evidence.subject_id,
                source_type=evidence.source_type,
                source_authority=evidence.source_authority,
                record_state=evidence.record_state,
                source_system=evidence.source_system,
                source_record_version=evidence.source_record_version,
                source_as_of=evidence.source_as_of,
                s3_key_reference=evidence.storage_key,
                cryptographic_hash=evidence.cryptographic_hash,
            )
        )
        await self.session.commit()

    async def create_system_record_evidence(
        self,
        evidence: Evidence,
        *,
        tenant_id: str,
        domain_id: str,
        mapping_id: str,
        record_fingerprint: str,
    ) -> bool:
        """Persist one approved source record once, even when an export is retried."""
        existing = await self.session.execute(
            select(DBEvidence.id).where(
                DBEvidence.tenant_id == tenant_id,
                DBEvidence.domain_id == domain_id,
                DBEvidence.source_mapping_id == mapping_id,
                DBEvidence.source_record_fingerprint == record_fingerprint,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return False
        self.session.add(DBEvidence(
            id=evidence.id,
            tenant_id=tenant_id,
            domain_id=domain_id,
            subject_id=evidence.subject_id,
            source_type=evidence.source_type,
            source_authority=evidence.source_authority,
            record_state=evidence.record_state,
            source_system=evidence.source_system,
            source_record_version=evidence.source_record_version,
            source_as_of=evidence.source_as_of,
            source_mapping_id=mapping_id,
            source_record_fingerprint=record_fingerprint,
            s3_key_reference=evidence.storage_key,
            cryptographic_hash=evidence.cryptographic_hash,
        ))
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            return False
        return True

    async def delete_evidence(
        self,
        evidence_id: str,
        *,
        tenant_id: str,
        domain_id: str,
        actor_id: str,
        reason: str,
        now: datetime | None = None
    ) -> bool:
        """Withdraw evidence from operational use by appending an immutable event."""
        current_time = now or datetime.now(timezone.utc)

        # Check if evidence exists and belongs to tenant
        result = await self.session.execute(
            select(DBEvidence).where(
                DBEvidence.id == evidence_id,
                DBEvidence.tenant_id == tenant_id,
                DBEvidence.domain_id == domain_id,
            )
        )
        evidence = result.scalars().first()
        if not evidence:
            return False

        # Check if already deleted
        deletion_result = await self.session.execute(
            select(DBEvidenceDeletionEvent).where(
                DBEvidenceDeletionEvent.evidence_id == evidence_id
            )
        )
        if deletion_result.scalars().first():
            return False

        self.session.add(
            DBEvidenceDeletionEvent(
                id="ev_del_" + uuid.uuid4().hex,
                evidence_id=evidence_id,
                tenant_id=tenant_id,
                domain_id=domain_id,
                actor_id=actor_id,
                reason=reason,
                timestamp=current_time
            )
        )
        await self.session.commit()
        return True

    async def get_evidence(
        self,
        evidence_id: str,
        *,
        tenant_id: str,
    ) -> Optional[StoredEvidence]:
        result = await self.session.execute(
            select(DBEvidence).where(
                DBEvidence.id == evidence_id,
                DBEvidence.tenant_id == tenant_id,
                ~exists().where(DBEvidenceDeletionEvent.evidence_id == DBEvidence.id)
            )
        )
        db_ev = result.scalars().first()
        if not db_ev:
            return None
            
        return StoredEvidence(
            evidence=Evidence(
                id=cast(str, db_ev.id),
                subject_id=cast(str, db_ev.subject_id),
                source_type=cast(Any, db_ev.source_type),
                storage_key=cast(Optional[str], db_ev.s3_key_reference),
                cryptographic_hash=cast(str, db_ev.cryptographic_hash),
                timestamp=db_ev.timestamp.isoformat() if db_ev.timestamp else "",
                source_authority=cast(Any, db_ev.source_authority),
                record_state=cast(Any, db_ev.record_state),
                source_system=cast(Optional[str], db_ev.source_system),
                source_record_version=cast(Optional[str], db_ev.source_record_version),
                source_as_of=cast(Optional[datetime], db_ev.source_as_of),
                retention_expires_at=cast(Optional[datetime], db_ev.retention_expires_at),
                deleted_at=cast(Optional[datetime], db_ev.deleted_at),
                deletion_reason=cast(Optional[str], db_ev.deletion_reason),
            ),
            tenant_id=cast(str, db_ev.tenant_id),
            domain_id=cast(str, db_ev.domain_id),
        )

    async def list_for_subject(
        self,
        *,
        tenant_id: str,
        domain_id: str,
        subject_id: str,
    ) -> list[dict[str, Any]]:
        """List evidence identifiers and metadata without returning source content."""
        result = await self.session.execute(
            select(DBEvidence)
            .where(
                DBEvidence.tenant_id == tenant_id,
                DBEvidence.domain_id == domain_id,
                DBEvidence.subject_id == subject_id,
                ~exists().where(DBEvidenceDeletionEvent.evidence_id == DBEvidence.id)
            )
            .order_by(DBEvidence.timestamp.desc(), DBEvidence.id)
        )
        return [
            {
                "evidence_id": cast(str, evidence.id),
                "source_type": cast(str, evidence.source_type),
                "captured_at": evidence.timestamp.isoformat() if evidence.timestamp else None,
                "source_authority": cast(str, evidence.source_authority),
                "record_state": cast(str, evidence.record_state),
                "source_system": cast(Optional[str], evidence.source_system),
                "source_as_of": evidence.source_as_of.isoformat() if evidence.source_as_of else None,
                "integrity_hash": cast(str, evidence.cryptographic_hash),
            }
            for evidence in result.scalars().all()
        ]


class EvidenceFactProposalRepository:
    """Persists independently reviewed facts without turning source extraction into evaluation."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _payload(proposal: DBEvidenceFactProposal) -> dict[str, Any]:
        return {
            "proposal_id": cast(str, proposal.id),
            "domain_id": cast(str, proposal.domain_id),
            "evidence_id": cast(str, proposal.evidence_id),
            "subject_id": cast(str, proposal.subject_id),
            "target_path": cast(str, proposal.target_path),
            "asserted_value": proposal.asserted_value,
            "source_quote": cast(str, proposal.source_quote),
            "source_locator": cast(Optional[str], proposal.source_locator),
            "proposal_origin": cast(str, proposal.proposal_origin),
            "evidence_sha256": cast(str, proposal.evidence_sha256),
            "input_sha256": cast(str, proposal.input_sha256),
            "status": cast(str, proposal.status),
            "proposed_by": cast(str, proposal.proposed_by),
            "reviewed_by": cast(Optional[str], proposal.reviewed_by),
            "review_note": cast(Optional[str], proposal.review_note),
            "reviewed_at": proposal.reviewed_at.isoformat() if proposal.reviewed_at else None,
            "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
        }

    async def create(
        self,
        *,
        tenant_id: str,
        domain_id: str,
        evidence: Evidence,
        target_path: str,
        asserted_value: Any,
        source_quote: str,
        source_locator: Optional[str],
        proposed_by: str,
    ) -> dict[str, Any]:
        canonical_input = json.dumps(
            {
                "tenant_id": tenant_id,
                "domain_id": domain_id,
                "evidence_id": evidence.id,
                "evidence_sha256": evidence.cryptographic_hash,
                "target_path": target_path,
                "asserted_value": asserted_value,
                "source_quote": source_quote,
                "source_locator": source_locator,
                "proposal_origin": "MANUAL",
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        proposal = DBEvidenceFactProposal(
            id="efp_" + uuid.uuid4().hex,
            tenant_id=tenant_id,
            domain_id=domain_id,
            evidence_id=evidence.id,
            subject_id=evidence.subject_id,
            target_path=target_path,
            asserted_value=asserted_value,
            source_quote=source_quote,
            source_locator=source_locator,
            extraction_confidence=1.0,
            source_trust_level=1.0,
            proposal_origin="MANUAL",
            evidence_sha256=evidence.cryptographic_hash,
            input_sha256=hashlib.sha256(canonical_input.encode("utf-8")).hexdigest(),
            proposed_by=proposed_by,
            status="PENDING",
        )
        self.session.add(proposal)
        self.session.add(
            DBEvidenceFactProposalEvent(
                id="efpe_" + uuid.uuid4().hex,
                proposal_id=proposal.id,
                tenant_id=tenant_id,
                domain_id=domain_id,
                sequence=1,
                action="SUBMITTED",
                actor_id=proposed_by,
                note="Evidence fact proposal submitted.",
            )
        )
        await self.session.commit()
        return self._payload(proposal)

    async def accept_confirmed_system_record(
        self,
        *,
        tenant_id: str,
        domain_id: str,
        evidence: Evidence,
        mapping_id: str,
        mapping_reviewer_id: str,
        values: dict[str, Any],
        source_system: str,
        source_record_version: str,
    ) -> None:
        """Accept declared facts through an independently approved source mapping.

        This is intentionally narrower than ordinary fact attestation. It may
        only be used for a *confirmed* system record and preserves the mapping
        reviewer's identity as the acceptance authority for every created fact.
        """
        if evidence.record_state != "confirmed" or evidence.source_authority != "official_system":
            raise EvidenceFactProposalConflictError(
                "Only confirmed records from an official system may use mapping-based acceptance."
            )
        accepted_at = datetime.now(timezone.utc)
        for target_path, asserted_value in values.items():
            canonical_input = json.dumps(
                {
                    "tenant_id": tenant_id,
                    "domain_id": domain_id,
                    "evidence_id": evidence.id,
                    "evidence_sha256": evidence.cryptographic_hash,
                    "target_path": target_path,
                    "asserted_value": asserted_value,
                    "mapping_id": mapping_id,
                    "proposal_origin": "CONFIRMED_SYSTEM_RECORD",
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
            proposal = DBEvidenceFactProposal(
                id="efp_" + uuid.uuid4().hex,
                tenant_id=tenant_id,
                domain_id=domain_id,
                evidence_id=evidence.id,
                subject_id=evidence.subject_id,
                target_path=target_path,
                asserted_value=asserted_value,
                source_quote=f"Confirmed {source_system} record version {source_record_version}.",
                source_locator=f"approved mapping {mapping_id}",
                extraction_confidence=1.0,
                source_trust_level=1.0,
                proposal_origin="CONFIRMED_SYSTEM_RECORD",
                evidence_sha256=evidence.cryptographic_hash,
                input_sha256=hashlib.sha256(canonical_input.encode("utf-8")).hexdigest(),
                proposed_by=f"system-record:{mapping_id}",
                status="ACCEPTED",
                reviewed_by=mapping_reviewer_id,
                review_note="Accepted through independently approved system-record mapping.",
                reviewed_at=accepted_at,
            )
            self.session.add(proposal)
            self.session.add(
                DBEvidenceFactProposalEvent(
                    id="efpe_" + uuid.uuid4().hex,
                    proposal_id=proposal.id,
                    tenant_id=tenant_id,
                    domain_id=domain_id,
                    sequence=1,
                    action="ACCEPTED",
                    actor_id=mapping_reviewer_id,
                    note="Accepted through independently approved system-record mapping.",
                )
            )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise EvidenceFactProposalConflictError(
                "The system record facts changed while they were being accepted."
            ) from exc

    async def get(
        self,
        proposal_id: str,
        *,
        tenant_id: str,
        domain_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        query = select(DBEvidenceFactProposal).where(
            DBEvidenceFactProposal.id == proposal_id,
            DBEvidenceFactProposal.tenant_id == tenant_id,
        )
        if domain_id is not None:
            query = query.where(DBEvidenceFactProposal.domain_id == domain_id)
        proposal = (await self.session.execute(query)).scalar_one_or_none()
        return self._payload(proposal) if proposal else None

    async def list_for_evidence(
        self,
        *,
        tenant_id: str,
        domain_id: str,
        evidence_id: str,
    ) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(DBEvidenceFactProposal)
            .where(
                DBEvidenceFactProposal.tenant_id == tenant_id,
                DBEvidenceFactProposal.domain_id == domain_id,
                DBEvidenceFactProposal.evidence_id == evidence_id,
            )
            .order_by(DBEvidenceFactProposal.created_at, DBEvidenceFactProposal.id)
        )
        return [self._payload(proposal) for proposal in result.scalars().all()]

    async def attest(
        self,
        *,
        proposal_id: str,
        tenant_id: str,
        domain_id: str,
        reviewer_id: str,
        action: str,
        note: str,
    ) -> Optional[dict[str, Any]]:
        proposal = (
            await self.session.execute(
                select(DBEvidenceFactProposal)
                .where(
                    DBEvidenceFactProposal.id == proposal_id,
                    DBEvidenceFactProposal.tenant_id == tenant_id,
                    DBEvidenceFactProposal.domain_id == domain_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if proposal is None:
            return None
        if proposal.status != "PENDING":
            raise EvidenceFactProposalConflictError("This evidence fact proposal has already been reviewed.")
        if proposal.proposed_by == reviewer_id:
            raise EvidenceFactProposalConflictError("A proposer cannot accept or reject their own evidence fact.")
        if action == "ACCEPT":
            accepted = (
                await self.session.execute(
                    select(DBEvidenceFactProposal.id).where(
                        DBEvidenceFactProposal.evidence_id == proposal.evidence_id,
                        DBEvidenceFactProposal.target_path == proposal.target_path,
                        DBEvidenceFactProposal.status == "ACCEPTED",
                    )
                )
            ).scalar_one_or_none()
            if accepted is not None:
                raise EvidenceFactProposalConflictError(
                    "An accepted fact already exists for this evidence and target. It cannot be overwritten; use a new evidence record and governed evaluation."
                )

        status = "ACCEPTED" if action == "ACCEPT" else "REJECTED"
        setattr(proposal, "status", status)
        setattr(proposal, "reviewed_by", reviewer_id)
        setattr(proposal, "review_note", note)
        setattr(proposal, "reviewed_at", datetime.now(timezone.utc))
        self.session.add(
            DBEvidenceFactProposalEvent(
                id="efpe_" + uuid.uuid4().hex,
                proposal_id=proposal.id,
                tenant_id=tenant_id,
                domain_id=domain_id,
                sequence=2,
                action=status,
                actor_id=reviewer_id,
                note=note,
            )
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise EvidenceFactProposalConflictError(
                "The evidence fact proposal changed while it was being reviewed."
            ) from exc
        return self._payload(proposal)

    async def accepted_claims_and_facts(
        self,
        *,
        tenant_id: str,
        domain_id: str,
        evidence_id: str,
        evidence_sha256: str,
    ) -> tuple[list[Claim], list[Fact]]:
        """Materialise deterministic facts only from independently accepted proposals."""
        result = await self.session.execute(
            select(DBEvidenceFactProposal)
            .where(
                DBEvidenceFactProposal.tenant_id == tenant_id,
                DBEvidenceFactProposal.domain_id == domain_id,
                DBEvidenceFactProposal.evidence_id == evidence_id,
                DBEvidenceFactProposal.evidence_sha256 == evidence_sha256,
                DBEvidenceFactProposal.status == "ACCEPTED",
            )
            .order_by(DBEvidenceFactProposal.created_at, DBEvidenceFactProposal.id)
        )
        claims: list[Claim] = []
        facts: list[Fact] = []
        for proposal in result.scalars().all():
            claim_id = "claim_" + cast(str, proposal.id)
            claims.append(
                Claim(
                    id=claim_id,
                    evidence_id=cast(str, proposal.evidence_id),
                    target_path=cast(str, proposal.target_path),
                    asserted_value=proposal.asserted_value,
                    extraction_confidence=cast(float, proposal.extraction_confidence),
                    source_trust_level=cast(float, proposal.source_trust_level),
                    status="resolved",
                    source_quote=cast(str, proposal.source_quote),
                    source_locator=(
                        f"proposal:{proposal.id}" + (
                            f"; {proposal.source_locator}" if proposal.source_locator else ""
                        )
                    ),
                )
            )
            facts.append(
                Fact(
                    id="fact_" + cast(str, proposal.id),
                    target_path=cast(str, proposal.target_path),
                    resolved_value=proposal.asserted_value,
                    final_confidence=1.0,
                    status="resolved",
                    supporting_claims=[claim_id],
                )
            )
        return claims, facts

class ReleaseRepository:
    """Async repository for fetching immutable releases and compiled RuleGraphs."""
    
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _release_from_row(db_release: DBRelease) -> Release:
        return Release(
            id=cast(str, db_release.id),
            domain_id=cast(str, db_release.domain_id),
            version=cast(str, db_release.version),
            rule_graph_id=cast(str, db_release.rule_graph_id),
            digital_signature=cast(str, db_release.digital_signature),
            signed_payload=cast(Dict[str, Any], db_release.signed_payload or {}),
            signed_payload_hash=cast(Optional[str], db_release.signed_payload_hash),
            signing_key_id=cast(Optional[str], db_release.signing_key_id),
            signing_public_key=cast(Optional[str], db_release.signing_public_key),
            effective_from=cast(Optional[date], db_release.effective_from),
            effective_until=cast(Optional[date], db_release.effective_until),
            applicability=cast(Dict[str, List[str]], db_release.applicability or {}),
            workflows=[WorkflowRule.model_validate(item) for item in cast(List[Dict[str, Any]], db_release.workflows or [])],
            source_manifest_hash=cast(Optional[str], db_release.source_manifest_hash),
        )

    async def get_release(self, domain_id: str, version: str) -> Optional[Release]:
        """Fetches the Release definition from the database."""
        result = await self.session.execute(
            select(DBRelease).where(
                DBRelease.domain_id == domain_id,
                DBRelease.version == version
            )
        )
        db_release = result.scalars().first()
        if not db_release:
            return None
        return self._release_from_row(db_release)

    async def get_release_by_id(self, release_id: str) -> Optional[Release]:
        result = await self.session.execute(select(DBRelease).where(DBRelease.id == release_id))
        db_release = result.scalars().first()
        return self._release_from_row(db_release) if db_release else None

    async def list_domain_releases(self, domain_id: str) -> list[Release]:
        result = await self.session.execute(
            select(DBRelease)
            .where(DBRelease.domain_id == domain_id)
            .order_by(DBRelease.effective_from.desc(), DBRelease.created_at.desc(), DBRelease.version.desc())
        )
        return [self._release_from_row(row) for row in result.scalars().all()]

    @staticmethod
    def _periods_overlap(
        existing_from: date,
        existing_until: Optional[date],
        incoming_from: date,
        incoming_until: Optional[date],
    ) -> bool:
        existing_end = existing_until or date.max
        incoming_end = incoming_until or date.max
        return existing_from <= incoming_end and incoming_from <= existing_end

    @staticmethod
    def _applicability_overlaps(
        existing: Dict[str, List[str]],
        incoming: Dict[str, List[str]],
    ) -> bool:
        # A missing constraint means "all values" for that selector. Two
        # contexts are distinct only when one shared selector has no overlap.
        for key in set(existing).intersection(incoming):
            if not set(existing[key]).intersection(incoming[key]):
                return False
        return True

    async def _ensure_applicability_available(self, release: Release) -> None:
        if release.effective_from is None:
            return
        rows = await self.session.execute(
            select(DBRelease).where(
                DBRelease.domain_id == release.domain_id,
                DBRelease.effective_from.is_not(None),
            )
        )
        for existing in rows.scalars().all():
            existing_from = cast(Optional[date], existing.effective_from)
            if existing_from is None:
                continue
            if self._periods_overlap(
                existing_from,
                cast(Optional[date], existing.effective_until),
                release.effective_from,
                release.effective_until,
            ) and self._applicability_overlaps(
                cast(Dict[str, List[str]], existing.applicability or {}),
                release.applicability,
            ):
                raise ReleaseApplicabilityConflictError(
                    "This release would overlap an existing effective policy for the same applicability context. "
                    "Close the earlier policy or make the applicability selectors disjoint."
                )

    async def create_release(
        self,
        release: Release,
        rule_graph: RuleGraph,
        compiled_bytecode: dict,
        *,
        draft_id: Optional[str] = None,
        approved_by: str | None = None,
        approved_at: datetime | None = None,
    ) -> None:
        """Persists a newly compiled, signed Release together with its RuleGraph.
        Both rows are immutable from this point on -- there is no update path."""
        await self._ensure_applicability_available(release)
        draft = None
        if draft_id is not None:
            result = await self.session.execute(
                select(DBPolicyDraft).where(DBPolicyDraft.id == draft_id).with_for_update()
            )
            draft = result.scalars().first()
            if draft is None or draft.status != "PENDING" or draft.domain_id != release.domain_id:
                raise DraftReleaseConflictError(
                    "The policy draft is no longer pending and cannot be released."
                )
        db_release = DBRelease(
            id=release.id,
            domain_id=release.domain_id,
            version=release.version,
            rule_graph_id=release.rule_graph_id,
            digital_signature=release.digital_signature,
            signed_payload=release.signed_payload,
            signed_payload_hash=release.signed_payload_hash,
            signing_key_id=release.signing_key_id,
            signing_public_key=release.signing_public_key,
            effective_from=release.effective_from,
            effective_until=release.effective_until,
            applicability=release.applicability,
            workflows=[workflow.model_dump(mode='json') for workflow in release.workflows],
            source_manifest_hash=release.source_manifest_hash,
        )
        db_rule_graph = DBRuleGraph(
            id=rule_graph.id,
            release_id=release.id,
            compiled_bytecode=compiled_bytecode
        )
        self.session.add(db_release)
        self.session.add(db_rule_graph)
        if draft is not None:
            setattr(draft, "status", "RELEASED")
            setattr(draft, "approved_by", approved_by)
            setattr(draft, "approved_at", approved_at or datetime.now(timezone.utc))
            setattr(draft, "released_as_release_id", release.id)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ReleaseVersionConflictError(
                f"Release version {release.version} already exists for domain {release.domain_id}."
            ) from exc

    async def get_compiled_rule_graph(self, rule_graph_id: str) -> Optional[RuleGraph]:
        """
        Fetches the compiled bytecode (RuleGraph) from the database.
        """
        result = await self.session.execute(
            select(DBRuleGraph).where(DBRuleGraph.id == rule_graph_id)
        )
        db_graph = result.scalars().first()
        if not db_graph:
            return None
            
        return RuleGraph(
            id=cast(str, db_graph.id),
            release_id=cast(str, db_graph.release_id),
            root_expression=build_expression_tree(cast(Dict[str, Any], db_graph.compiled_bytecode)),
            compiled_at=db_graph.compiled_at.isoformat() if db_graph.compiled_at else ""
        )


class ReasoningRepository:
    """Async repository for persisting and retrieving dynamic ReasoningGraphs."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        
    async def save_evaluation_artifacts(
        self,
        *,
        graph: ReasoningGraph,
        overall_decision: str,
        overall_confidence: float,
        tenant_id: str,
        domain_id: str,
        release_id: str,
        evidence_id: str,
        claims: List[Claim],
        facts: List[Fact],
        release: Release | None = None,
    ) -> str:
        """Persists a trace and its complete epistemic lineage atomically."""
        db_graph = DBReasoningGraph(
            id=graph.id,
            tenant_id=tenant_id,
            domain_id=domain_id,
            subject_id=graph.subject_id,
            rule_graph_id=graph.rule_graph_id,
            release_id=release_id,
            evidence_id=evidence_id,
            graph_data=graph.model_dump(mode='json'),
            overall_decision=overall_decision,
            overall_confidence=overall_confidence,
            # Application time retains microsecond ordering on SQLite as well as Postgres.
            evaluated_at=datetime.now(timezone.utc),
        )
        self.session.add(db_graph)

        for claim in claims:
            self.session.add(
                DBClaim(
                    id=claim.id,
                    tenant_id=tenant_id,
                    domain_id=domain_id,
                    evidence_id=claim.evidence_id,
                    reasoning_graph_id=graph.id,
                    target_path=claim.target_path,
                    asserted_value=claim.asserted_value,
                    extraction_confidence=claim.extraction_confidence,
                    source_trust_level=claim.source_trust_level,
                    status=claim.status,
                    source_quote=claim.source_quote,
                    source_locator=claim.source_locator,
                )
            )

        for fact in facts:
            self.session.add(
                DBFact(
                    id=fact.id,
                    tenant_id=tenant_id,
                    domain_id=domain_id,
                    reasoning_graph_id=graph.id,
                    target_path=fact.target_path,
                    resolved_value=fact.resolved_value,
                    final_confidence=fact.final_confidence,
                    status=fact.status,
                    supporting_claim_ids=fact.supporting_claims,
                    rejected_claim_ids=fact.rejected_claims,
                )
            )

        if release is not None:
            for workflow in release.workflows:
                triggered = (
                    workflow.trigger_condition == "overall == pass" and overall_decision == "ELIGIBLE"
                ) or (
                    workflow.trigger_condition == "overall == fail" and overall_decision == "INELIGIBLE"
                )
                if not triggered:
                    continue
                idempotency_key = hashlib.sha256(
                    f"{tenant_id}:{release.id}:{graph.id}:{workflow.id}".encode("utf-8")
                ).hexdigest()
                self.session.add(
                    DBWorkflowOutbox(
                        id="wfout_" + uuid.uuid4().hex,
                        tenant_id=tenant_id,
                        domain_id=domain_id,
                        release_id=release.id,
                        reasoning_graph_id=graph.id,
                        workflow_id=workflow.id,
                        action_type=workflow.action_type,
                        action_payload=workflow.action_payload,
                        idempotency_key=idempotency_key,
                        status="HELD",
                    )
                )

        await self.session.commit()
        return cast(str, db_graph.id)

    async def supersede_fact(
        self,
        old_fact_id: str,
        new_fact_id: str,
        *,
        tenant_id: str,
        domain_id: str,
        actor_id: str,
        reason: str,
        now: datetime | None = None
    ) -> bool:
        """Append a historical fact relationship without mutating either fact."""
        current_time = now or datetime.now(timezone.utc)

        # Check if old fact exists and belongs to tenant/domain
        result = await self.session.execute(
            select(DBFact).where(
                DBFact.id == old_fact_id,
                DBFact.tenant_id == tenant_id,
                DBFact.domain_id == domain_id
            )
        )
        old_fact = result.scalars().first()
        if not old_fact:
            return False

        # Check if new fact exists and belongs to tenant/domain
        new_result = await self.session.execute(
            select(DBFact).where(
                DBFact.id == new_fact_id,
                DBFact.tenant_id == tenant_id,
                DBFact.domain_id == domain_id
            )
        )
        new_fact = new_result.scalars().first()
        if not new_fact or old_fact_id == new_fact_id:
            return False
        if new_fact.reasoning_graph_id != old_fact.reasoning_graph_id:
            return False

        # Check if already superseded
        super_result = await self.session.execute(
            select(DBFactSupersessionEvent).where(
                DBFactSupersessionEvent.old_fact_id == old_fact_id
            )
        )
        if super_result.scalars().first():
            return False

        self.session.add(
            DBFactSupersessionEvent(
                id="fact_sup_" + uuid.uuid4().hex,
                old_fact_id=old_fact_id,
                new_fact_id=new_fact_id,
                tenant_id=tenant_id,
                domain_id=domain_id,
                actor_id=actor_id,
                reason=reason,
                timestamp=current_time
            )
        )
        await self.session.commit()
        return True

    async def get_reasoning_graph(
        self,
        graph_id: str,
        *,
        tenant_id: str,
    ) -> Optional[ReasoningGraph]:
        """Retrieves a previously computed evaluation trace."""
        result = await self.session.execute(
            select(DBReasoningGraph).where(
                DBReasoningGraph.id == graph_id,
                DBReasoningGraph.tenant_id == tenant_id,
                ~exists().where(DBReasoningGraphDeletionEvent.reasoning_graph_id == DBReasoningGraph.id)
            )
        )
        db_graph = result.scalars().first()
        if not db_graph:
            return None
            
        data = cast(Dict[str, Any], db_graph.graph_data)
        
        return ReasoningGraph.model_validate(data)

    async def list_subject_current_positions(
        self,
        *,
        tenant_id: str,
        subject_id: str,
    ) -> list[dict[str, Any]]:
        """Return the newest visible engine position for each configured domain.

        This is deliberately a read model over immutable traces, not a student
        information system record or a new source of institutional truth.
        """
        result = await self.session.execute(
            select(DBReasoningGraph, DBDomain)
            .join(DBDomain, DBDomain.id == DBReasoningGraph.domain_id)
            .where(
                DBReasoningGraph.tenant_id == tenant_id,
                DBReasoningGraph.subject_id == subject_id,
                DBDomain.tenant_id == tenant_id,
                ~exists().where(
                    DBReasoningGraphDeletionEvent.reasoning_graph_id == DBReasoningGraph.id
                ),
            )
            .order_by(DBReasoningGraph.evaluated_at.desc(), DBReasoningGraph.id.desc())
        )
        newest_by_domain: dict[str, dict[str, Any]] = {}
        for graph, domain in result.all():
            domain_id = cast(str, graph.domain_id)
            if domain_id in newest_by_domain:
                continue
            schema = cast(dict[str, Any], domain.schema_definition)
            # New domains use subject-neutral wording. Existing curriculum
            # domains retain their earlier key until their next approved draft.
            surface = schema.get("subject_position", schema.get("student_position", {}))
            surface = surface if isinstance(surface, dict) else {}
            presentation = _domain_presentation(schema)
            graph_data = cast(dict[str, Any], graph.graph_data)
            evaluation_context = graph_data.get("evaluation_context", {})
            evaluation_context = evaluation_context if isinstance(evaluation_context, dict) else {}
            casework = schema.get("casework", {})
            casework = casework if isinstance(casework, dict) else {}
            source_system = evaluation_context.get("source_system")
            source = None
            if isinstance(source_system, str) and source_system:
                source = (await self.session.execute(select(DBInstitutionalDataSource).where(
                    DBInstitutionalDataSource.tenant_id == tenant_id,
                    DBInstitutionalDataSource.domain_id == domain_id,
                    DBInstitutionalDataSource.display_name == source_system,
                    DBInstitutionalDataSource.status == "APPROVED",
                ))).scalars().first()
            source_as_of = evaluation_context.get("source_as_of")
            source_expected_by = None
            if source is not None and source.expected_refresh_hours and isinstance(source_as_of, str):
                try:
                    as_of = datetime.fromisoformat(source_as_of.replace("Z", "+00:00"))
                    as_of = as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)
                    source_expected_by = as_of + timedelta(hours=cast(int, source.expected_refresh_hours))
                except ValueError:
                    source_expected_by = None
            escalation_hours = casework.get("escalation_after_hours", 72)
            if isinstance(escalation_hours, bool) or not isinstance(escalation_hours, int) or escalation_hours < 1:
                escalation_hours = 72
            provisional_escalation_by = None
            if isinstance(source_as_of, str):
                try:
                    as_of = datetime.fromisoformat(source_as_of.replace("Z", "+00:00"))
                    as_of = as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)
                    provisional_escalation_by = as_of + timedelta(hours=escalation_hours)
                except ValueError:
                    provisional_escalation_by = None
            newest_by_domain[domain_id] = {
                "trace_id": cast(str, graph.id),
                "domain_id": domain_id,
                "domain_name": cast(str, domain.name),
                "position_type": str(surface.get("type", "other")),
                "position_label": str(surface.get("label", domain.name)),
                "governed_person_label": presentation["governed_person_label"],
                "position_collection_label": presentation["position_collection_label"],
                "decision": cast(str, graph.overall_decision),
                "release_version": str(evaluation_context.get("release_version", "Recorded release")),
                "source_authority": str(evaluation_context.get("source_authority", "subject_submitted")),
                "record_state": str(evaluation_context.get("record_state", "provisional")),
                "source_system": source_system,
                "source_as_of": source_as_of,
                "source_expected_by": source_expected_by.isoformat() if source_expected_by else None,
                "source_is_stale": bool(source_expected_by and source_expected_by < datetime.now(timezone.utc)),
                "responsible_group": casework.get("primary_group"),
                "fallback_group": casework.get("fallback_group"),
                "provisional_escalation_by": provisional_escalation_by.isoformat() if provisional_escalation_by else None,
                "evaluated_at": graph.evaluated_at.isoformat() if graph.evaluated_at else None,
            }
        return list(newest_by_domain.values())

    async def list_subject_information(
        self,
        *,
        tenant_id: str,
        subject_id: str,
    ) -> list[dict[str, Any]]:
        """Return a subject-safe view of governed information and decision use.

        This is a read model over evidence-fact proposals and saved decision
        snapshots. It intentionally omits source blobs, storage keys, hashes,
        record fingerprints, staff notes, and raw database identifiers that are
        not needed for a student's explanation journey.
        """
        proposal_result = await self.session.execute(
            select(DBEvidenceFactProposal, DBEvidence, DBDomain)
            .join(DBEvidence, DBEvidence.id == DBEvidenceFactProposal.evidence_id)
            .join(DBDomain, DBDomain.id == DBEvidenceFactProposal.domain_id)
            .where(
                DBEvidenceFactProposal.tenant_id == tenant_id,
                DBEvidenceFactProposal.subject_id == subject_id,
                DBEvidence.tenant_id == tenant_id,
                DBEvidence.subject_id == subject_id,
                DBDomain.tenant_id == tenant_id,
                DBEvidenceFactProposal.status.in_(["ACCEPTED", "PENDING"]),
                ~exists().where(DBEvidenceDeletionEvent.evidence_id == DBEvidence.id),
            )
            .order_by(DBDomain.name, DBEvidenceFactProposal.target_path, DBEvidenceFactProposal.created_at)
        )
        proposal_rows = proposal_result.all()
        if not proposal_rows:
            return []

        pending_values_by_target: dict[tuple[str, str], set[str]] = {}
        for proposal, _evidence, _domain in proposal_rows:
            if proposal.status != "PENDING":
                continue
            key = (cast(str, proposal.domain_id), cast(str, proposal.target_path))
            pending_values_by_target.setdefault(key, set()).add(json.dumps(proposal.asserted_value, sort_keys=True, default=str))

        graph_result = await self.session.execute(
            select(DBReasoningGraph, DBDomain)
            .join(DBDomain, DBDomain.id == DBReasoningGraph.domain_id)
            .where(
                DBReasoningGraph.tenant_id == tenant_id,
                DBReasoningGraph.subject_id == subject_id,
                DBDomain.tenant_id == tenant_id,
                ~exists().where(DBReasoningGraphDeletionEvent.reasoning_graph_id == DBReasoningGraph.id),
            )
            .order_by(DBReasoningGraph.evaluated_at.desc(), DBReasoningGraph.id.desc())
        )
        graph_rows = graph_result.all()
        graph_by_id = {cast(str, graph.id): (graph, domain) for graph, domain in graph_rows}
        graph_ids = list(graph_by_id.keys())
        facts_by_claim_id: dict[str, list[tuple[DBFact, DBReasoningGraph, DBDomain]]] = {}
        if graph_ids:
            facts_result = await self.session.execute(
                select(DBFact)
                .where(
                    DBFact.tenant_id == tenant_id,
                    DBFact.reasoning_graph_id.in_(graph_ids),
                    ~exists().where(DBFactSupersessionEvent.old_fact_id == DBFact.id),
                )
                .order_by(DBFact.created_at, DBFact.id)
            )
            for fact in facts_result.scalars().all():
                graph_domain = graph_by_id.get(cast(str, fact.reasoning_graph_id))
                if graph_domain is None:
                    continue
                graph, domain = graph_domain
                supporting_claims = cast(list[str], fact.supporting_claim_ids or [])
                for claim_id in supporting_claims:
                    facts_by_claim_id.setdefault(claim_id, []).append((fact, graph, domain))

        items: list[dict[str, Any]] = []
        for proposal, evidence, domain in proposal_rows:
            schema = cast(dict[str, Any], domain.schema_definition)
            labels = _domain_fact_labels(schema)
            presentation = _domain_presentation(schema)
            proposal_id = cast(str, proposal.id)
            target_path = cast(str, proposal.target_path)
            conflicting = len(pending_values_by_target.get((cast(str, proposal.domain_id), target_path), set())) > 1
            status, status_label, status_explanation = _student_information_status(
                cast(str, proposal.status),
                conflicting=conflicting,
            )
            used_in: list[dict[str, Any]] = []
            for fact, graph, graph_domain in facts_by_claim_id.get("claim_" + proposal_id, []):
                graph_schema = cast(dict[str, Any], graph_domain.schema_definition)
                surface = graph_schema.get("subject_position", graph_schema.get("student_position", {}))
                surface = surface if isinstance(surface, dict) else {}
                graph_data = cast(dict[str, Any], graph.graph_data)
                evaluation_context = graph_data.get("evaluation_context", {})
                evaluation_context = evaluation_context if isinstance(evaluation_context, dict) else {}
                used_in.append({
                    "trace_id": cast(str, graph.id),
                    "domain_id": cast(str, graph.domain_id),
                    "position_label": str(surface.get("label", graph_domain.name)),
                    "decision": cast(str, graph.overall_decision),
                    "release_version": str(evaluation_context.get("release_version", "Recorded release")),
                    "evaluated_at": graph.evaluated_at.isoformat() if graph.evaluated_at else None,
                    "fact_status": cast(str, fact.status),
                })

            items.append({
                "information_id": stable_information_reference(
                    tenant_id=tenant_id,
                    domain_id=cast(str, proposal.domain_id),
                    subject_id=subject_id,
                    fact_id="fact_" + proposal_id,
                ),
                "domain_id": cast(str, proposal.domain_id),
                "domain_name": cast(str, domain.name),
                "label": labels.get(target_path, target_path.removeprefix("facts.").replace("_", " ").title()),
                "value": proposal.asserted_value,
                "status": status,
                "status_label": status_label,
                "status_explanation": status_explanation,
                "proposed_at": proposal.created_at.isoformat() if proposal.created_at else None,
                "reviewed_at": proposal.reviewed_at.isoformat() if proposal.reviewed_at else None,
                "source": {
                    "authority": cast(str, evidence.source_authority),
                    "record_state": cast(str, evidence.record_state),
                    "type": cast(str, evidence.source_type),
                    "system": cast(Optional[str], evidence.source_system),
                    "as_of": evidence.source_as_of.isoformat() if evidence.source_as_of else None,
                    "captured_at": evidence.timestamp.isoformat() if evidence.timestamp else None,
                    "reference": _safe_source_reference(proposal, evidence),
                },
                "used_in": used_in,
                "governed_person_label": presentation["governed_person_label"],
            })
        return items
    async def get_evaluation_artifacts(
        self,
        graph_id: str,
        *,
        tenant_id: str,
    ) -> Optional[StoredEvaluationArtifacts]:
        """Load the complete immutable input/output set required for verification."""
        result = await self.session.execute(
            select(DBReasoningGraph).where(
                DBReasoningGraph.id == graph_id,
                DBReasoningGraph.tenant_id == tenant_id,
            )
        )
        stored_graph = result.scalars().first()
        if stored_graph is None:
            return None
        release_id = cast(Optional[str], stored_graph.release_id)
        evidence_id = cast(Optional[str], stored_graph.evidence_id)
        if release_id is None or evidence_id is None:
            return None
        claims = await self.get_claims(graph_id, tenant_id=tenant_id)
        facts = await self.get_facts(graph_id, tenant_id=tenant_id)
        return StoredEvaluationArtifacts(
            graph=ReasoningGraph.model_validate(cast(Dict[str, Any], stored_graph.graph_data)),
            tenant_id=cast(str, stored_graph.tenant_id),
            domain_id=cast(str, stored_graph.domain_id),
            subject_id=cast(str, stored_graph.subject_id),
            release_id=release_id,
            evidence_id=evidence_id,
            overall_decision=cast(str, stored_graph.overall_decision),
            overall_confidence=cast(float, stored_graph.overall_confidence),
            claims=claims,
            facts=facts,
        )

    async def get_claims(
        self,
        reasoning_graph_id: str,
        *,
        tenant_id: str,
    ) -> list[Claim]:
        result = await self.session.execute(
            select(DBClaim)
            .where(
                DBClaim.reasoning_graph_id == reasoning_graph_id,
                DBClaim.tenant_id == tenant_id,
            )
            .order_by(DBClaim.created_at, DBClaim.id)
        )
        return [
            Claim(
                id=cast(str, row.id),
                evidence_id=cast(str, row.evidence_id),
                target_path=cast(str, row.target_path),
                asserted_value=row.asserted_value,
                extraction_confidence=cast(float, row.extraction_confidence),
                source_trust_level=cast(float, row.source_trust_level),
                status=cast(Any, row.status),
                source_quote=cast(Optional[str], row.source_quote),
                source_locator=cast(Optional[str], row.source_locator),
            )
            for row in result.scalars().all()
        ]

    async def get_facts(
        self,
        reasoning_graph_id: str,
        *,
        tenant_id: str,
    ) -> list[Fact]:
        result = await self.session.execute(
            select(DBFact)
            .where(
                DBFact.reasoning_graph_id == reasoning_graph_id,
                DBFact.tenant_id == tenant_id,
                ~exists().where(DBFactSupersessionEvent.old_fact_id == DBFact.id)
            )
            .order_by(DBFact.created_at, DBFact.id)
        )
        return [
            Fact(
                id=cast(str, row.id),
                target_path=cast(str, row.target_path),
                resolved_value=row.resolved_value,
                final_confidence=cast(float, row.final_confidence),
                status=cast(Any, row.status),
                supporting_claims=cast(List[str], row.supporting_claim_ids),
                rejected_claims=cast(List[str], row.rejected_claim_ids),
                retention_expires_at=cast(Optional[datetime], row.retention_expires_at),
                deleted_at=cast(Optional[datetime], row.deleted_at),
                deletion_reason=cast(Optional[str], row.deletion_reason),
                superseded_by_fact_id=cast(Optional[str], row.superseded_by_fact_id),
                superseded_at=cast(Optional[datetime], row.superseded_at),
                superseding_reason=cast(Optional[str], row.superseding_reason),
            )
            for row in result.scalars().all()
        ]
