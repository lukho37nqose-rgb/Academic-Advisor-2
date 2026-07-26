from __future__ import annotations

import base64
import asyncio
from copy import deepcopy
from datetime import date

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import app
from app.core.compiler import compile_release_to_graph
from app.core.crypto import CryptoService
from app.core.models import Release, RuleGraph
from app.infrastructure.database import get_db_session
from app.infrastructure.db import Base
from app.infrastructure.repositories import ReleaseRepository
from app.services.auth import Role, UserIdentity, get_current_user
from app.services.release_integrity import (
    ReleaseIntegrityError,
    require_release_integrity_for_evaluation,
    verify_release_bundle,
)


def _signing_key() -> str:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return base64.b64encode(pem).decode("ascii")


def _signed_release(monkeypatch: pytest.MonkeyPatch) -> tuple[Release, RuleGraph]:
    monkeypatch.setenv("GOVERNANCE_PRIVATE_KEY", _signing_key())
    monkeypatch.setenv("GOVERNANCE_KEY_ID", "assurance-signing-key-2026")
    policy = {
        "root": {
            "id": "eligible_rule",
            "label": "Current status is active",
            "target": "status.active",
            "condition": "==",
            "value": True,
            "source_citation": "Policy section 4.1",
        }
    }
    release_id = "rel_assurance"
    graph = compile_release_to_graph(release_id, policy)
    payload = {
        "policy": policy,
        "release": {
            "id": release_id,
            "domain_id": "dom_assurance",
            "version": "2026.1",
            "rule_graph_id": graph.id,
            "effective_from": "2026-01-01",
            "effective_until": None,
            "applicability": {"entry_year": ["2026"]},
        },
    }
    crypto = CryptoService()
    signature, payload_hash = crypto.sign_payload(payload)
    return (
        Release(
            id=release_id,
            domain_id="dom_assurance",
            version="2026.1",
            rule_graph_id=graph.id,
            digital_signature=signature,
            signed_payload=payload,
            signed_payload_hash=payload_hash,
            signing_key_id=crypto.key_id,
            signing_public_key=crypto.public_key_pem,
            effective_from=date(2026, 1, 1),
            applicability={"entry_year": ["2026"]},
        ),
        graph,
    )


def test_complete_release_bundle_binds_policy_metadata_and_compiled_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    release, graph = _signed_release(monkeypatch)

    assert verify_release_bundle(release, graph) == (True, "verified")


@pytest.mark.parametrize(
    "change",
    [
        lambda release: release.model_copy(update={"version": "2026.2"}),
        lambda release: release.model_copy(update={"effective_from": date(2026, 2, 1)}),
        lambda release: release.model_copy(update={"applicability": {"entry_year": ["2027"]}}),
        lambda release: release.model_copy(update={"rule_graph_id": "rg_substituted"}),
    ],
)
def test_changed_release_metadata_invalidates_the_bundle(
    monkeypatch: pytest.MonkeyPatch,
    change,
) -> None:
    release, graph = _signed_release(monkeypatch)

    valid, reason = verify_release_bundle(change(release), graph)

    assert not valid
    assert "differs" in reason


def test_changed_signed_policy_or_compiled_graph_invalidates_the_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    release, graph = _signed_release(monkeypatch)
    altered_payload = deepcopy(release.signed_payload)
    altered_payload["policy"]["root"]["value"] = False
    altered_policy_release = release.model_copy(update={"signed_payload": altered_payload})
    altered_graph = compile_release_to_graph(
        release.id,
        {
            "root": {
                "id": "eligible_rule",
                "label": "Current status is active",
                "target": "status.active",
                "condition": "==",
                "value": False,
                "source_citation": "Policy section 4.1",
            }
        },
    )

    assert verify_release_bundle(altered_policy_release, graph) == (False, "release signature verification failed")
    assert verify_release_bundle(release, altered_graph) == (False, "persisted compiled graph differs from the signed policy")


def test_production_evaluation_rejects_legacy_or_tampered_release(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IRE_ENV", "production")
    release, graph = _signed_release(monkeypatch)

    legacy = release.model_copy(update={"signed_payload": {}, "signed_payload_hash": None})
    with pytest.raises(ReleaseIntegrityError, match="complete signing"):
        require_release_integrity_for_evaluation(legacy, graph)

    with pytest.raises(ReleaseIntegrityError, match="compiled graph"):
        require_release_integrity_for_evaluation(
            release,
            compile_release_to_graph(
                release.id,
                {"root": {"target": "status.active", "condition": "==", "value": False}},
            ),
        )


def test_evaluation_route_rejects_a_signed_release_with_a_substituted_compiled_graph(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release, graph = _signed_release(monkeypatch)
    altered_policy = {
        "root": {
            "id": "eligible_rule",
            "label": "Current status is active",
            "target": "status.active",
            "condition": "==",
            "value": False,
            "source_citation": "Policy section 4.1",
        }
    }
    altered_graph = compile_release_to_graph(release.id, altered_policy).model_copy(update={"id": graph.id})
    database_path = tmp_path / "evaluation_release_integrity.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            await ReleaseRepository(session).create_release(
                release,
                altered_graph,
                altered_policy["root"],
            )

    async def test_db_session():
        async with session_factory() as session:
            yield session

    asyncio.run(prepare())
    monkeypatch.setenv("IRE_ENV", "production")
    app.dependency_overrides[get_current_user] = lambda: UserIdentity(
        tenant_id="tenant_assurance",
        role=Role.TENANT_ADMIN,
        user_id="admin_1",
        domain_ids=[],
    )
    app.dependency_overrides[get_db_session] = test_db_session
    try:
        response = TestClient(app).post(
            "/api/v1/evaluate",
            headers={"Idempotency-Key": "substituted-graph-assurance-test"},
            json={
                "rule_graph_id": graph.id,
                "evidence_id": "evidence_not_reached",
                "subject_id": "subject_1",
                "domain_id": release.domain_id,
                "release_version": release.version,
                "as_of_date": "2026-06-01",
                "applicability_context": {"entry_year": "2026"},
            },
        )
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert response.status_code == 409
    assert response.json()["detail"] == "The selected release failed integrity verification and cannot be evaluated."
