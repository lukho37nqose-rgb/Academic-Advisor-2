from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import app
from app.core.lineage import stable_information_reference
from app.core.models import Claim, EvaluationContext, Evidence, Fact, ReasoningGraph
from app.infrastructure.database import get_db_session
from app.infrastructure.db import Base, DBDomain, DBEvidence, DBEvidenceFactProposal, DBTenant
from app.infrastructure.repositories import EvidenceRepository, ReasoningRepository
from app.services.auth import Role, UserIdentity, get_current_user


async def _create_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def _subject_identity(
    subject_id: str = "subject_1",
    *,
    domain_ids: list[str] | None = None,
    role: Role = Role.SUBJECT,
) -> UserIdentity:
    return UserIdentity(
        tenant_id="tenant_info",
        role=role,
        user_id=f"identity_{subject_id}",
        subject_id=subject_id if role == Role.SUBJECT else None,
        domain_ids=domain_ids or ["dom_progression"],
    )


async def _store_information_fixture(session_factory) -> None:
    async with session_factory() as session:
        session.add(DBTenant(id="tenant_info", name="Information Institution"))
        session.add(DBTenant(id="tenant_other", name="Other Institution"))
        session.add(
            DBDomain(
                id="dom_progression",
                tenant_id="tenant_info",
                name="Academic progression",
                schema_definition={
                    "type": "object",
                    "properties": {
                        "facts": {
                            "type": "object",
                            "properties": {
                                "completed_credits": {"type": "number", "title": "Completed credits"},
                                "registration_status": {"type": "string", "title": "Registration status"},
                            },
                        },
                    },
                    "student_position": {"type": "curriculum", "label": "Progression position"},
                    "presentation": {"governed_person_label": "student"},
                },
            )
        )
        session.add(
            DBDomain(
                id="dom_hidden",
                tenant_id="tenant_info",
                name="Hidden domain",
                schema_definition={"type": "object"},
            )
        )
        session.add(
            DBDomain(
                id="dom_other",
                tenant_id="tenant_other",
                name="Other domain",
                schema_definition={"type": "object"},
            )
        )
        await session.commit()

        evidence_repository = EvidenceRepository(session)
        await evidence_repository.create_evidence(
            Evidence(
                id="evidence_credits",
                subject_id="subject_1",
                source_type="system_record_export",
                storage_key="secret-storage-key",
                cryptographic_hash="secret-hash-value",
                timestamp="2026-07-24T08:00:00+00:00",
                source_authority="official_system",
                record_state="confirmed",
                source_system="PeopleSoft",
                source_record_version="2026-07-24",
                source_as_of=datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc),
            ),
            tenant_id="tenant_info",
            domain_id="dom_progression",
        )
        evidence_credits = await session.get(DBEvidence, "evidence_credits")
        assert evidence_credits is not None
        evidence_credits.source_record_fingerprint = "secret-record-fingerprint"
        await session.commit()
        await evidence_repository.create_evidence(
            Evidence(
                id="evidence_pending",
                subject_id="subject_1",
                source_type="user_input",
                storage_key="pending-secret-storage-key",
                cryptographic_hash="pending-secret-hash",
                timestamp="2026-07-25T08:00:00+00:00",
            ),
            tenant_id="tenant_info",
            domain_id="dom_progression",
        )
        await evidence_repository.create_evidence(
            Evidence(
                id="evidence_other_subject",
                subject_id="subject_2",
                source_type="system_record_export",
                storage_key="other-subject-storage-key",
                cryptographic_hash="other-subject-secret-hash",
                timestamp="2026-07-24T08:00:00+00:00",
            ),
            tenant_id="tenant_info",
            domain_id="dom_progression",
        )
        await evidence_repository.create_evidence(
            Evidence(
                id="evidence_hidden_domain",
                subject_id="subject_1",
                source_type="system_record_export",
                storage_key="hidden-domain-storage-key",
                cryptographic_hash="hidden-domain-secret-hash",
                timestamp="2026-07-24T08:00:00+00:00",
            ),
            tenant_id="tenant_info",
            domain_id="dom_hidden",
        )
        session.add(
            DBEvidence(
                id="evidence_other_tenant",
                tenant_id="tenant_other",
                domain_id="dom_other",
                subject_id="subject_1",
                source_type="system_record_export",
                source_authority="official_system",
                record_state="confirmed",
                source_system="OtherTenantSIS",
                s3_key_reference="other-tenant-storage-key",
                cryptographic_hash="other-tenant-secret-hash",
                source_record_fingerprint="other-tenant-fingerprint",
            )
        )

        session.add_all([
            DBEvidenceFactProposal(
                id="efp_completed_credits",
                tenant_id="tenant_info",
                domain_id="dom_progression",
                evidence_id="evidence_credits",
                subject_id="subject_1",
                target_path="facts.completed_credits",
                asserted_value=252,
                source_quote="Completed credits: 252.",
                source_locator="Transcript page 2",
                extraction_confidence=1.0,
                source_trust_level=1.0,
                proposal_origin="MANUAL",
                evidence_sha256="secret-hash-value",
                input_sha256="input-hash",
                proposed_by="records_1",
                status="ACCEPTED",
                reviewed_by="approver_1",
                review_note="staff-only acceptance note",
                reviewed_at=datetime(2026, 7, 24, 9, 0, tzinfo=timezone.utc),
            ),
            DBEvidenceFactProposal(
                id="efp_registration_pending",
                tenant_id="tenant_info",
                domain_id="dom_progression",
                evidence_id="evidence_pending",
                subject_id="subject_1",
                target_path="facts.registration_status",
                asserted_value="pending",
                source_quote="Registration status pending.",
                source_locator="Student submission form",
                extraction_confidence=0.8,
                source_trust_level=0.7,
                proposal_origin="MANUAL",
                evidence_sha256="pending-secret-hash",
                input_sha256="pending-input-hash",
                proposed_by="records_1",
                status="PENDING",
            ),
            DBEvidenceFactProposal(
                id="efp_other_subject",
                tenant_id="tenant_info",
                domain_id="dom_progression",
                evidence_id="evidence_other_subject",
                subject_id="subject_2",
                target_path="facts.completed_credits",
                asserted_value=12,
                source_quote="Other subject credits.",
                extraction_confidence=1.0,
                source_trust_level=1.0,
                proposal_origin="MANUAL",
                evidence_sha256="other-subject-secret-hash",
                input_sha256="other-input-hash",
                proposed_by="records_1",
                status="ACCEPTED",
            ),
            DBEvidenceFactProposal(
                id="efp_hidden_domain",
                tenant_id="tenant_info",
                domain_id="dom_hidden",
                evidence_id="evidence_hidden_domain",
                subject_id="subject_1",
                target_path="facts.hidden",
                asserted_value="hidden",
                source_quote="Hidden domain fact.",
                extraction_confidence=1.0,
                source_trust_level=1.0,
                proposal_origin="MANUAL",
                evidence_sha256="hidden-domain-secret-hash",
                input_sha256="hidden-input-hash",
                proposed_by="records_1",
                status="ACCEPTED",
            ),
            DBEvidenceFactProposal(
                id="efp_other_tenant",
                tenant_id="tenant_other",
                domain_id="dom_other",
                evidence_id="evidence_other_tenant",
                subject_id="subject_1",
                target_path="facts.completed_credits",
                asserted_value=999,
                source_quote="Other tenant credits.",
                extraction_confidence=1.0,
                source_trust_level=1.0,
                proposal_origin="MANUAL",
                evidence_sha256="other-tenant-secret-hash",
                input_sha256="other-tenant-input-hash",
                proposed_by="records_1",
                status="ACCEPTED",
            ),
        ])
        await session.commit()

        graph = ReasoningGraph(
            id="trace_progression",
            subject_id="subject_1",
            rule_graph_id="rule_graph_progression",
            evaluation_context=EvaluationContext(
                tenant_id="tenant_info",
                domain_id="dom_progression",
                subject_id="subject_1",
                release_version="2026.1",
                source_authority="official_system",
                record_state="confirmed",
                source_system="PeopleSoft",
                source_as_of=datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc),
            ),
        )
        await ReasoningRepository(session).save_evaluation_artifacts(
            graph=graph,
            overall_decision="ELIGIBLE",
            overall_confidence=1.0,
            tenant_id="tenant_info",
            domain_id="dom_progression",
            release_id="release_progression",
            evidence_id="evidence_credits",
            claims=[
                Claim(
                    id="claim_efp_completed_credits",
                    evidence_id="evidence_credits",
                    target_path="facts.completed_credits",
                    asserted_value=252,
                    extraction_confidence=1.0,
                    source_trust_level=1.0,
                    status="resolved",
                ),
            ],
            facts=[
                Fact(
                    id="fact_efp_completed_credits",
                    target_path="facts.completed_credits",
                    resolved_value=252,
                    final_confidence=1.0,
                    status="resolved",
                    supporting_claims=["claim_efp_completed_credits"],
                ),
            ],
        )
        similar_value_graph = ReasoningGraph(
            id="trace_similar_value_without_lineage",
            subject_id="subject_1",
            rule_graph_id="rule_graph_progression",
            evaluation_context=EvaluationContext(
                tenant_id="tenant_info",
                domain_id="dom_progression",
                subject_id="subject_1",
                release_version="2026.1",
            ),
        )
        await ReasoningRepository(session).save_evaluation_artifacts(
            graph=similar_value_graph,
            overall_decision="ELIGIBLE",
            overall_confidence=1.0,
            tenant_id="tenant_info",
            domain_id="dom_progression",
            release_id="release_progression",
            evidence_id="evidence_credits",
            claims=[],
            facts=[
                Fact(
                    id="fact_same_target_and_value_without_proposal_lineage",
                    target_path="facts.completed_credits",
                    resolved_value=252,
                    final_confidence=1.0,
                    status="resolved",
                    supporting_claims=["claim_unrelated"],
                ),
            ],
        )


def test_subject_information_exposes_governed_information_without_raw_evidence_or_secrets(tmp_path):
    database_path = tmp_path / "subject_information.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))
    asyncio.run(_store_information_fixture(session_factory))

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _test_db_session
    app.dependency_overrides[get_current_user] = lambda: _subject_identity()
    try:
        response = TestClient(app).get("/api/v1/subject/information", params={"subject_id": "subject_2"})
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert response.status_code == 200
    payload = response.json()
    completed_reference = stable_information_reference(
        tenant_id="tenant_info",
        domain_id="dom_progression",
        subject_id="subject_1",
        fact_id="fact_efp_completed_credits",
    )
    pending_reference = stable_information_reference(
        tenant_id="tenant_info",
        domain_id="dom_progression",
        subject_id="subject_1",
        fact_id="fact_efp_registration_pending",
    )
    assert [item["information_id"] for item in payload["items"]] == [
        completed_reference,
        pending_reference,
    ]
    accepted = payload["items"][0]
    assert "proposal_id" not in accepted
    assert "target_path" not in accepted
    assert accepted["label"] == "Completed credits"
    assert accepted["value"] == 252
    assert accepted["status"] == "accepted"
    assert accepted["source"]["authority"] == "official_system"
    assert accepted["source"]["record_state"] == "confirmed"
    assert accepted["source"]["type"] == "system_record_export"
    assert accepted["source"]["system"] == "PeopleSoft"
    assert accepted["source"]["as_of"].startswith("2026-07-24T08:00:00")
    assert accepted["source"]["reference"] == "Transcript page 2"
    assert [usage["trace_id"] for usage in accepted["used_in"]] == ["trace_progression"]
    assert accepted["used_in"][0]["position_label"] == "Progression position"
    assert payload["items"][1]["status"] == "provisional"

    serialized = json.dumps(payload)
    for secret in [
        "secret-storage-key",
        "secret-hash-value",
        "secret-record-fingerprint",
        "pending-secret-storage-key",
        "other-subject-secret-hash",
        "hidden-domain-secret-hash",
        "other-tenant-secret-hash",
        "other-tenant-storage-key",
        "evidence_credits",
        "evidence_other_subject",
        "evidence_other_tenant",
        "efp_completed_credits",
        "staff-only acceptance note",
        "facts.completed_credits",
        "trace_similar_value_without_lineage",
    ]:
        assert secret not in serialized


def test_subject_information_respects_domain_assignment_and_subject_role(tmp_path):
    database_path = tmp_path / "subject_information_access.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))
    asyncio.run(_store_information_fixture(session_factory))

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _test_db_session
    try:
        app.dependency_overrides[get_current_user] = lambda: _subject_identity(domain_ids=["dom_hidden"])
        hidden_domain_response = TestClient(app).get("/api/v1/subject/information")

        app.dependency_overrides[get_current_user] = lambda: _subject_identity(role=Role.STAFF_MEMBER)
        staff_response = TestClient(app).get("/api/v1/subject/information")
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert hidden_domain_response.status_code == 200
    assert [item["domain_id"] for item in hidden_domain_response.json()["items"]] == ["dom_hidden"]
    assert staff_response.status_code == 403
