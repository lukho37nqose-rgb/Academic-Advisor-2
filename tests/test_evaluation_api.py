from __future__ import annotations

import asyncio
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import app
from app.core.compiler import compile_release_to_graph
from app.core.crypto import CryptoService
from app.core.models import ReasoningGraph, Release
from app.infrastructure.database import get_db_session
from app.infrastructure.db import Base, DBDomain, DBTenant
from app.infrastructure.blob_storage import BlobStorage
from app.infrastructure.repositories import ReleaseRepository
from app.services.auth import Role, UserIdentity, get_current_user
from app.services.policy_source_manifest import build_policy_source_manifest


async def _create_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def test_evaluation_persists_tenant_scoped_claims_and_facts(tmp_path, monkeypatch):
    database_path = tmp_path / "evaluation.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))

    policy_payload = {
        "root": {
            "id": "mock_claim_rule",
            "label": "Mock extracted claim is present",
            "target": "facts.mock",
            "condition": "==",
            "value": "Extracted claim from evidence.",
            "source_citation": "Reference policy section 1",
        }
    }
    rule_graph = compile_release_to_graph("rel_eval", policy_payload)
    source_manifest, source_manifest_hash = build_policy_source_manifest(policy_payload)
    
    payload = {
        "policy": policy_payload,
        "release": {
            "id": "rel_eval",
            "domain_id": "dom_curr_2026",
            "version": "2026.1",
            "rule_graph_id": rule_graph.id,
            "effective_from": "2026-01-01",
            "effective_until": "2026-12-31",
            "applicability": {"entry_year": ["2026"]},
            "source_manifest_hash": source_manifest_hash,
        },
        "source_manifest": source_manifest,
    }
    
    # Generate a real signing key for the test
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode("utf-8")
    monkeypatch.setenv("GOVERNANCE_PRIVATE_KEY", pem)
    monkeypatch.setenv("GOVERNANCE_KEY_ID", "test-key-id")
    
    crypto = CryptoService()
    signature, payload_hash = crypto.sign_payload(payload)

    async def _store_release() -> None:
        async with session_factory() as session:
            session.add(DBTenant(id="tenant_demo_uni", name="Demo University"))
            session.add(
                DBDomain(
                    id="dom_curr_2026",
                    tenant_id="tenant_demo_uni",
                    name="Curriculum 2026",
                    schema_definition={
                        "type": "object",
                        "properties": {
                            "facts": {
                                "type": "object",
                                "properties": {
                                    "mock": {
                                        "type": "string",
                                        "title": "Mock extracted claim",
                                    }
                                },
                            }
                        },
                    },
                )
            )
            await session.commit()
            await ReleaseRepository(session).create_release(
                Release(
                    id="rel_eval",
                    domain_id="dom_curr_2026",
                    version="2026.1",
                    rule_graph_id=rule_graph.id,
                    digital_signature=signature,
                    signed_payload=payload,
                    signed_payload_hash=payload_hash,
                    signing_key_id=crypto.key_id,
                    signing_public_key=crypto.public_key_pem,
                    effective_from=date(2026, 1, 1),
                    effective_until=date(2026, 12, 31),
                    applicability={"entry_year": ["2026"]},
                    source_manifest_hash=source_manifest_hash,
                ),
                rule_graph,
                policy_payload["root"],
            )

    asyncio.run(_store_release())

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    def _tenant_admin() -> UserIdentity:
        return UserIdentity(
            tenant_id="tenant_demo_uni",
            role=Role.TENANT_ADMIN,
            user_id="admin_1",
            domain_ids=[],
        )

    app.dependency_overrides[get_current_user] = _tenant_admin
    app.dependency_overrides[get_db_session] = _test_db_session
    try:
        client = TestClient(app)
        ingestion = client.post(
            "/api/v1/evidence",
            json={
                "domain_id": "dom_curr_2026",
                "subject_id": "subject_1",
                "content": "Evidence used to exercise the deterministic evaluation path.",
            },
        )
        evidence_id = ingestion.json()["id"]
        evidence_sources = client.get(
            "/api/v1/governance/evidence",
            params={"domain_id": "dom_curr_2026", "subject_id": "subject_1"},
        )
        fact_fields = client.get("/api/v1/admin/domains/dom_curr_2026/fact-fields")
        missing_date = client.post(
            "/api/v1/evaluate",
            headers={"Idempotency-Key": "evaluation-missing-date-test-key"},
            json={
                "rule_graph_id": rule_graph.id,
                "evidence_id": evidence_id,
                "subject_id": "subject_1",
                "domain_id": "dom_curr_2026",
                "release_version": "2026.1",
                "applicability_context": {"entry_year": "2026"},
            },
        )
        unreviewed_evaluation = client.post(
            "/api/v1/evaluate",
            headers={"Idempotency-Key": "evaluation-unreviewed-facts-test-key"},
            json={
                "rule_graph_id": rule_graph.id,
                "evidence_id": evidence_id,
                "subject_id": "subject_1",
                "domain_id": "dom_curr_2026",
                "release_version": "2026.1",
                "as_of_date": "2026-06-01",
                "applicability_context": {"entry_year": "2026"},
            },
        )
        proposal = client.post(
            "/api/v1/governance/evidence-fact-proposals",
            json={
                "domain_id": "dom_curr_2026",
                "evidence_id": evidence_id,
                "target_path": "facts.mock",
                "asserted_value": "Extracted claim from evidence.",
                "source_quote": "Evidence used to exercise the deterministic evaluation path.",
                "source_locator": "Reference evidence",
            },
        )
        self_attestation = client.post(
            f"/api/v1/governance/evidence-fact-proposals/{proposal.json()['proposal_id']}/attest",
            json={
                "domain_id": "dom_curr_2026",
                "action": "ACCEPT",
                "note": "This must be rejected because it is self-attestation.",
            },
        )
        app.dependency_overrides[get_current_user] = lambda: UserIdentity(
            tenant_id="tenant_demo_uni",
            role=Role.APPROVER,
            user_id="owner_1",
            domain_ids=["dom_curr_2026"],
        )
        attestation = client.post(
            f"/api/v1/governance/evidence-fact-proposals/{proposal.json()['proposal_id']}/attest",
            json={
                "domain_id": "dom_curr_2026",
                "action": "ACCEPT",
                "note": "The source quotation and declared field have been independently verified.",
            },
        )
        app.dependency_overrides[get_current_user] = _tenant_admin
        evaluation = client.post(
            "/api/v1/evaluate",
            headers={"Idempotency-Key": "evaluation-api-test-key"},
            json={
                "rule_graph_id": rule_graph.id,
                "evidence_id": evidence_id,
                "subject_id": "subject_1",
                "domain_id": "dom_curr_2026",
                "release_version": "2026.1",
                "as_of_date": "2026-06-01",
                "applicability_context": {"entry_year": "2026"},
            },
        )
        graph_id = evaluation.json()["reasoning_graph_id"]
        claims = client.get("/api/v1/claims", params={"graph_id": graph_id})
        facts = client.get("/api/v1/facts", params={"graph_id": graph_id})
        reasoning = client.get(f"/api/v1/reasoning/{graph_id}")
        replay = client.get(f"/api/v1/replay/{graph_id}")
        replacement_proposal = client.post(
            "/api/v1/governance/evidence-fact-proposals",
            json={
                "domain_id": "dom_curr_2026",
                "evidence_id": evidence_id,
                "target_path": "facts.mock",
                "asserted_value": "Different asserted value.",
                "source_quote": "A later assertion that must not overwrite an accepted fact.",
            },
        )
        app.dependency_overrides[get_current_user] = lambda: UserIdentity(
            tenant_id="tenant_demo_uni",
            role=Role.APPROVER,
            user_id="owner_1",
            domain_ids=["dom_curr_2026"],
        )
        duplicate_acceptance = client.post(
            f"/api/v1/governance/evidence-fact-proposals/{replacement_proposal.json()['proposal_id']}/attest",
            json={
                "domain_id": "dom_curr_2026",
                "action": "ACCEPT",
                "note": "This target already has an independently accepted evidence fact.",
            },
        )
        app.dependency_overrides[get_current_user] = _tenant_admin

        app.dependency_overrides[get_current_user] = lambda: UserIdentity(
            tenant_id="tenant_other",
            role=Role.TENANT_ADMIN,
            user_id="admin_other",
            domain_ids=[],
        )
        cross_tenant_cached_evaluation = client.post(
            "/api/v1/evaluate",
            headers={"Idempotency-Key": "evaluation-api-test-key"},
            json={
                "rule_graph_id": rule_graph.id,
                "evidence_id": evidence_id,
                "subject_id": "subject_1",
                "domain_id": "dom_curr_2026",
                "release_version": "2026.1",
                "as_of_date": "2026-06-01",
                "applicability_context": {"entry_year": "2026"},
            },
        )
        app.dependency_overrides[get_current_user] = _tenant_admin

        def incomplete_trace(context, graph, facts):
            return ReasoningGraph(
                id="trace_incomplete",
                subject_id=context.subject_id,
                rule_graph_id=graph.id,
                evaluation_context=context,
            )

        monkeypatch.setattr("app.api.generate_reasoning_graph", incomplete_trace)
        incomplete_evaluation = client.post(
            "/api/v1/evaluate",
            headers={"Idempotency-Key": "evaluation-incomplete-trace-test-key"},
            json={
                "rule_graph_id": rule_graph.id,
                "evidence_id": evidence_id,
                "subject_id": "subject_1",
                "domain_id": "dom_curr_2026",
                "release_version": "2026.1",
                "as_of_date": "2026-06-01",
                "applicability_context": {"entry_year": "2026"},
            },
        )
        BlobStorage._store[ingestion.json()["storage_key"]] = b"tampered evidence bytes"
        tampered_evaluation = client.post(
            "/api/v1/evaluate",
            headers={"Idempotency-Key": "evaluation-tampered-evidence-test-key"},
            json={
                "rule_graph_id": rule_graph.id,
                "evidence_id": evidence_id,
                "subject_id": "subject_1",
                "domain_id": "dom_curr_2026",
                "release_version": "2026.1",
                "as_of_date": "2026-06-01",
                "applicability_context": {"entry_year": "2026"},
            },
        )
        tampered_replay = client.get(f"/api/v1/replay/{graph_id}")
        app.dependency_overrides[get_current_user] = lambda: UserIdentity(
            tenant_id="tenant_demo_uni",
            role=Role.SUBJECT,
            user_id="identity_1",
            subject_id="subject_1",
            domain_ids=["dom_curr_2026"],
        )
        cross_subject_ingestion = client.post(
            "/api/v1/evidence",
            json={
                "domain_id": "dom_curr_2026",
                "subject_id": "subject_2",
                "content": "This must never be accepted for another subject.",
            },
        )
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert ingestion.status_code == 201
    assert ingestion.json()["storage_key"].startswith("tenants/tenant_demo_uni/evidence/")
    assert evidence_sources.status_code == 200
    assert evidence_sources.json()["items"][0]["evidence_id"] == evidence_id
    assert fact_fields.status_code == 200
    assert fact_fields.json()["items"] == [{"target_path": "facts.mock", "label": "Mock extracted claim", "schema_type": "string"}]
    assert missing_date.status_code == 422
    assert "as_of_date" in missing_date.json()["detail"]
    assert unreviewed_evaluation.status_code == 409
    assert "independently accepted facts" in unreviewed_evaluation.json()["detail"]
    assert proposal.status_code == 201
    assert self_attestation.status_code == 409
    assert attestation.status_code == 200
    assert attestation.json()["status"] == "ACCEPTED"
    assert evaluation.status_code == 202
    assert evaluation.json()["decision"] == "ELIGIBLE"
    assert cross_tenant_cached_evaluation.status_code == 404
    assert claims.status_code == 200
    assert claims.json()["items"][0]["evidence_id"] == evidence_id
    assert facts.status_code == 200
    assert facts.json()["items"][0]["supporting_claims"] == [claims.json()["items"][0]["id"]]
    assert reasoning.json()["evaluation_context"]["policy_as_of_date"] == "2026-06-01"
    assert reasoning.json()["evaluation_context"]["policy_context"] == {"entry_year": "2026"}
    assert replay.status_code == 200
    assert replay.json()["status"] == "VERIFIED"
    assert replay.json()["decision"] == "ELIGIBLE"
    assert replacement_proposal.status_code == 201
    assert duplicate_acceptance.status_code == 409
    assert incomplete_evaluation.status_code == 500
    assert incomplete_evaluation.json()["detail"] == "Evaluation did not produce a complete reasoning trace."
    assert tampered_evaluation.status_code == 409
    assert "integrity verification" in tampered_evaluation.json()["detail"]
    assert tampered_replay.status_code == 409
    assert "integrity verification" in tampered_replay.json()["detail"]
    assert cross_subject_ingestion.status_code == 403
