from __future__ import annotations

import asyncio
from datetime import date

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import app
from app.core.compiler import compile_release_to_graph
from app.core.crypto import CryptoService
from app.core.models import Release
from app.infrastructure.database import get_db_session
from app.infrastructure.db import Base, DBDomain, DBTenant
from app.infrastructure.repositories import ReleaseRepository
from app.services.auth import Role, UserIdentity, get_current_user
from app.services.policy_source_manifest import build_policy_source_manifest


TENANT_ID = "tenant_timeline"
DOMAIN_ID = "dom_timeline"
RELEASE_ID = "rel_timeline"


async def _create_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def _identity(role: Role, user_id: str, subject_id: str | None = None) -> UserIdentity:
    return UserIdentity(
        tenant_id=TENANT_ID,
        role=role,
        user_id=user_id,
        subject_id=subject_id,
        domain_ids=[DOMAIN_ID],
    )


def _private_key_pem() -> str:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")


async def _seed_signed_release(session_factory) -> None:
    policy = {
        "root": {
            "id": "progression_requirement",
            "label": "Progression requirement",
            "target": "facts.credits",
            "condition": ">=",
            "value": 96,
            "source_citation": "Programme Progression Policy, section 4",
        }
    }
    rule_graph = compile_release_to_graph(RELEASE_ID, policy)
    effective_from = date(2026, 1, 1)
    source_manifest, source_manifest_hash = build_policy_source_manifest(policy)
    signed_payload = {
        "policy": policy,
        "release": {
            "id": RELEASE_ID,
            "domain_id": DOMAIN_ID,
            "version": "2026.1",
            "rule_graph_id": rule_graph.id,
            "effective_from": effective_from.isoformat(),
            "effective_until": None,
            "applicability": {},
            "source_manifest_hash": source_manifest_hash,
        },
        "source_manifest": source_manifest,
    }
    crypto = CryptoService()
    signature, payload_hash = crypto.sign_payload(signed_payload)
    async with session_factory() as session:
        session.add(DBTenant(id=TENANT_ID, name="Timeline institution"))
        session.add(
            DBDomain(
                id=DOMAIN_ID,
                tenant_id=TENANT_ID,
                name="Academic progression",
                schema_definition={"type": "object", "properties": {}},
            )
        )
        await ReleaseRepository(session).create_release(
            Release(
                id=RELEASE_ID,
                domain_id=DOMAIN_ID,
                version="2026.1",
                rule_graph_id=rule_graph.id,
                digital_signature=signature,
                signed_payload=signed_payload,
                signed_payload_hash=payload_hash,
                signing_key_id=crypto.key_id,
                signing_public_key=crypto.public_key_pem,
                effective_from=effective_from,
                source_manifest_hash=source_manifest_hash,
            ),
            rule_graph,
            policy["root"],
        )


def _event_payload(
    *,
    title: str,
    visibility: str = "SUBJECT",
    predecessor_event_id: str | None = None,
    predecessor_relationship: str | None = None,
) -> dict[str, object]:
    return {
        "domain_id": DOMAIN_ID,
        "subject_id": "subject_1",
        "event_type": "CONCESSION" if predecessor_event_id is None else "REGISTRATION_POSITION",
        "title": title,
        "student_summary": "An authorised faculty decision was recorded for the student's academic position.",
        "institutional_effect": "The recorded position remains applicable until a later authorised institutional decision changes it.",
        "authority_name": "Faculty academic committee",
        "authority_reference": "Committee decision register 2026-14",
        "source_reference": "Institutional decision record 2026-14",
        "event_date": "2026-02-12",
        "effective_from": "2026-02-12",
        "visibility": visibility,
        "policy_release_id": RELEASE_ID,
        "policy_citation": "Programme Progression Policy, section 4",
        **({"predecessor_event_id": predecessor_event_id} if predecessor_event_id else {}),
        **({"predecessor_relationship": predecessor_relationship} if predecessor_relationship else {}),
    }


def test_institutional_timeline_preserves_certified_history_and_subject_privacy(tmp_path, monkeypatch):
    monkeypatch.setenv("GOVERNANCE_PRIVATE_KEY", _private_key_pem())
    monkeypatch.setenv("GOVERNANCE_KEY_ID", "timeline-test-key")
    database_path = tmp_path / "institutional_timeline.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))
    asyncio.run(_seed_signed_release(session_factory))

    current_user = _identity(Role.STAFF_MEMBER, "records_1")

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    def _current_user() -> UserIdentity:
        return current_user

    app.dependency_overrides[get_current_user] = _current_user
    app.dependency_overrides[get_db_session] = _test_db_session
    try:
        client = TestClient(app)
        submitted = client.post(
            "/api/v1/governance/institutional-context-events",
            json=_event_payload(title="Progression concession recorded"),
        )
        event_id = submitted.json()["event_id"]

        current_user = _identity(Role.SUBJECT, "subject_identity_1", "subject_1")
        pending_subject_timeline = client.get("/api/v1/institutional-timeline")

        current_user = _identity(Role.STAFF_MEMBER, "records_1")
        recorder_attestation = client.post(
            f"/api/v1/governance/institutional-context-events/{event_id}/attest",
            json={"domain_id": DOMAIN_ID, "action": "CERTIFY", "note": "A records steward must not certify an institutional context event."},
        )

        current_user = _identity(Role.TENANT_ADMIN, "records_1")
        self_attestation = client.post(
            f"/api/v1/governance/institutional-context-events/{event_id}/attest",
            json={"domain_id": DOMAIN_ID, "action": "CERTIFY", "note": "The recorder must not certify their own institutional context event."},
        )
        current_user = _identity(Role.APPROVER, "approver_1")
        certified = client.post(
            f"/api/v1/governance/institutional-context-events/{event_id}/attest",
            json={"domain_id": DOMAIN_ID, "action": "CERTIFY", "note": "Authority reference and the subject-safe explanation were independently verified."},
        )

        current_user = _identity(Role.STAFF_MEMBER, "records_1")
        staff_only_submission = client.post(
            "/api/v1/governance/institutional-context-events",
            json=_event_payload(title="Internal committee handling note", visibility="STAFF_ONLY"),
        )
        staff_only_id = staff_only_submission.json()["event_id"]
        current_user = _identity(Role.APPROVER, "approver_1")
        staff_only_certified = client.post(
            f"/api/v1/governance/institutional-context-events/{staff_only_id}/attest",
            json={"domain_id": DOMAIN_ID, "action": "CERTIFY", "note": "The internal-only handling record was independently verified."},
        )

        current_user = _identity(Role.STAFF_MEMBER, "records_1")
        revocation_submission = client.post(
            "/api/v1/governance/institutional-context-events",
            json=_event_payload(
                title="Progression concession concluded",
                predecessor_event_id=event_id,
                predecessor_relationship="REVOKES",
            ),
        )
        revocation_id = revocation_submission.json()["event_id"]
        current_user = _identity(Role.APPROVER, "approver_1")
        revocation_certified = client.post(
            f"/api/v1/governance/institutional-context-events/{revocation_id}/attest",
            json={"domain_id": DOMAIN_ID, "action": "CERTIFY", "note": "The later committee decision concludes the earlier concession."},
        )

        current_user = _identity(Role.SUBJECT, "subject_identity_1", "subject_1")
        subject_timeline = client.get("/api/v1/institutional-timeline")
        current_user = _identity(Role.SUBJECT, "subject_identity_2", "subject_2")
        other_subject_timeline = client.get("/api/v1/institutional-timeline")
        current_user = _identity(Role.AUDITOR, "auditor_1")
        staff_timeline = client.get(
            "/api/v1/governance/institutional-timeline",
            params={"domain_id": DOMAIN_ID, "subject_id": "subject_1"},
        )
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert submitted.status_code == 201
    assert submitted.json()["status"] == "SUBMITTED"
    assert pending_subject_timeline.json()["items"] == []
    assert recorder_attestation.status_code == 403
    assert self_attestation.status_code == 409
    assert "cannot attest" in self_attestation.json()["detail"]
    assert certified.status_code == 200
    assert certified.json()["status"] == "CERTIFIED"
    assert staff_only_submission.status_code == 201
    assert staff_only_certified.status_code == 200
    assert revocation_submission.status_code == 201
    assert revocation_certified.status_code == 200
    assert subject_timeline.status_code == 200
    assert len(subject_timeline.json()["items"]) == 2
    timeline_by_id = {item["event_id"]: item for item in subject_timeline.json()["items"]}
    assert timeline_by_id[event_id]["timeline_state"] == "REVOKED"
    assert timeline_by_id[event_id]["policy_release_version"] == "2026.1"
    assert "source_reference" not in timeline_by_id[event_id]
    assert "subject_id" not in timeline_by_id[event_id]
    assert all(item["visibility"] == "SUBJECT" for item in subject_timeline.json()["items"])
    assert other_subject_timeline.json()["items"] == []
    assert staff_timeline.status_code == 200
    assert len(staff_timeline.json()["items"]) == 3
    assert any(item["event_id"] == staff_only_id and item["visibility"] == "STAFF_ONLY" for item in staff_timeline.json()["items"])
    assert all("source_reference" in item for item in staff_timeline.json()["items"])
