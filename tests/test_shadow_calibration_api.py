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


TENANT_ID = "tenant_calibration"
DOMAIN_ID = "dom_calibration"
RELEASE_ID = "rel_calibration"


async def _create_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def _identity(role: Role, user_id: str) -> UserIdentity:
    return UserIdentity(
        tenant_id=TENANT_ID,
        role=role,
        user_id=user_id,
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
            "id": "gpa_requirement",
            "label": "Academic progress requirement",
            "target": "facts.gpa",
            "condition": ">=",
            "value": 3.0,
            "source_citation": "Academic Progress Policy, section 3.1",
        }
    }
    rule_graph = compile_release_to_graph(RELEASE_ID, policy)
    effective_from = date(2026, 1, 1)
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
        },
    }
    crypto = CryptoService()
    signature, payload_hash = crypto.sign_payload(signed_payload)
    async with session_factory() as session:
        session.add(DBTenant(id=TENANT_ID, name="Calibration institution"))
        session.add(
            DBDomain(
                id=DOMAIN_ID,
                tenant_id=TENANT_ID,
                name="Academic progression",
                schema_definition={
                    "type": "object",
                    "properties": {
                        "facts": {
                            "type": "object",
                            "properties": {"gpa": {"type": "number", "title": "Grade point average"}},
                        }
                    },
                },
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
            ),
            rule_graph,
            policy["root"],
        )


def _suite_payload(recorded_decision: str, case_reference: str) -> dict[str, object]:
    return {
        "domain_id": DOMAIN_ID,
        "release_id": RELEASE_ID,
        "name": f"Progression calibration {case_reference}",
        "description": "Compare a representative recorded outcome with the signed progression release.",
        "data_basis": "SYNTHETIC",
        "policy_as_of_date": "2026-06-01",
        "cases": [
            {
                "case_reference": case_reference,
                "description": "Representative progression case without a subject identifier.",
                "recorded_decision": recorded_decision,
                "recorded_outcome_reference": "Synthetic calibration register, entry 12",
                "facts": [{"target_path": "facts.gpa", "value": 3.5}],
            }
        ],
    }


def test_shadow_calibration_requires_independent_certification_and_preserves_mismatches(tmp_path, monkeypatch):
    monkeypatch.setenv("GOVERNANCE_PRIVATE_KEY", _private_key_pem())
    monkeypatch.setenv("GOVERNANCE_KEY_ID", "calibration-test-key")
    database_path = tmp_path / "shadow_calibration.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))
    asyncio.run(_seed_signed_release(session_factory))

    current_user = _identity(Role.RULE_AUTHOR, "author_1")

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    def _current_user() -> UserIdentity:
        return current_user

    app.dependency_overrides[get_current_user] = _current_user
    app.dependency_overrides[get_db_session] = _test_db_session
    try:
        client = TestClient(app)
        releases = client.get(f"/api/v1/governance/domains/{DOMAIN_ID}/calibration-releases")
        missing_privacy_approval = _suite_payload("ELIGIBLE", "case_deidentified_01")
        missing_privacy_approval["data_basis"] = "APPROVED_DEIDENTIFIED"
        rejected_deidentified_submission = client.post(
            "/api/v1/governance/shadow-calibrations",
            json=missing_privacy_approval,
        )
        submitted = client.post(
            "/api/v1/governance/shadow-calibrations",
            json=_suite_payload("ELIGIBLE", "case_match_01"),
        )
        suite_id = submitted.json()["suite_id"]
        current_user = _identity(Role.TENANT_ADMIN, "author_1")
        self_certification = client.post(
            f"/api/v1/governance/shadow-calibrations/{suite_id}/certify",
            json={"domain_id": DOMAIN_ID, "note": "The author should not be allowed to certify this suite."},
        )

        current_user = _identity(Role.POLICY_OWNER, "owner_1")
        certified = client.post(
            f"/api/v1/governance/shadow-calibrations/{suite_id}/certify",
            json={"domain_id": DOMAIN_ID, "note": "Verified recorded outcome references and representative case inputs."},
        )
        current_user = _identity(Role.RULE_AUTHOR, "author_1")
        completed = client.post(
            f"/api/v1/governance/shadow-calibrations/{suite_id}/run",
            json={"domain_id": DOMAIN_ID},
        )

        mismatch_submission = client.post(
            "/api/v1/governance/shadow-calibrations",
            json=_suite_payload("INELIGIBLE", "case_mismatch_01"),
        )
        mismatch_suite_id = mismatch_submission.json()["suite_id"]
        current_user = _identity(Role.POLICY_OWNER, "owner_1")
        mismatch_certified = client.post(
            f"/api/v1/governance/shadow-calibrations/{mismatch_suite_id}/certify",
            json={"domain_id": DOMAIN_ID, "note": "Verified the differing recorded outcome for this representative case."},
        )
        current_user = _identity(Role.RULE_AUTHOR, "author_1")
        mismatch_run = client.post(
            f"/api/v1/governance/shadow-calibrations/{mismatch_suite_id}/run",
            json={"domain_id": DOMAIN_ID},
        )
        mismatch_detail = client.get(
            f"/api/v1/governance/shadow-calibrations/{mismatch_suite_id}",
            params={"domain_id": DOMAIN_ID},
        )
        finding_id = mismatch_detail.json()["findings"][0]["finding_id"]
        current_user = _identity(Role.TENANT_ADMIN, "author_1")
        self_resolution = client.patch(
            f"/api/v1/governance/shadow-calibration-findings/{finding_id}",
            json={
                "domain_id": DOMAIN_ID,
                "classification": "POLICY_MODEL",
                "note": "The author should not classify a mismatch in their own calibration suite.",
            },
        )
        current_user = _identity(Role.POLICY_OWNER, "owner_1")
        resolved = client.patch(
            f"/api/v1/governance/shadow-calibration-findings/{finding_id}",
            json={
                "domain_id": DOMAIN_ID,
                "classification": "POLICY_MODEL",
                "note": "The historical outcome relied on a transitional provision not yet represented in this release.",
            },
        )
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert releases.status_code == 200
    assert releases.json()["items"] == [{
        "release_id": RELEASE_ID,
        "version": "2026.1",
        "effective_from": "2026-01-01",
        "effective_until": None,
        "calibration_ready": True,
        "calibration_blocker": None,
    }]
    assert rejected_deidentified_submission.status_code == 422
    assert "privacy approval reference" in str(rejected_deidentified_submission.json()["detail"]).lower()
    assert submitted.status_code == 201
    assert submitted.json()["status"] == "SUBMITTED"
    assert submitted.json()["data_basis"] == "SYNTHETIC"
    assert self_certification.status_code == 409
    assert "cannot certify their own" in self_certification.json()["detail"]
    assert certified.status_code == 200
    assert certified.json()["status"] == "CERTIFIED"
    assert completed.status_code == 200
    assert completed.json()["run"]["report"]["all_cases_passed"] is True
    assert "No institutional record or operative decision was changed" in completed.json()["message"]
    assert mismatch_submission.status_code == 201
    assert mismatch_certified.status_code == 200
    assert mismatch_run.status_code == 200
    assert mismatch_run.json()["run"]["report"]["all_cases_passed"] is False
    assert mismatch_detail.json()["findings"][0]["status"] == "OPEN"
    assert self_resolution.status_code == 409
    assert "cannot classify their own" in self_resolution.json()["detail"]
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "RESOLVED"
    assert resolved.json()["classification"] == "POLICY_MODEL"
