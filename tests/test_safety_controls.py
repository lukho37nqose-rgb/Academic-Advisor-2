from __future__ import annotations

import asyncio
import base64
from datetime import date
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import app
from app.core.compiler import compile_release_to_graph
from app.core.crypto import CryptoService
from app.core.models import Release
from app.infrastructure.database import get_db_session
from app.infrastructure.db import Base
from app.infrastructure.repositories import (
    GovernancePublicationBusyError,
    ReleaseRepository,
    acquire_domain_governance_lock,
)
from app.services.auth import Role, UserIdentity, get_current_user
from app.services.policy_source_manifest import build_policy_source_manifest


def _signing_key() -> str:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return base64.b64encode(pem).decode("ascii")


def test_release_signature_bundle_detects_changed_policy_material(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GOVERNANCE_PRIVATE_KEY", _signing_key())
    monkeypatch.setenv("GOVERNANCE_KEY_ID", "test-governance-key-2026")
    crypto = CryptoService()
    payload = {"policy": {"root": "rule"}, "release": {"version": "2026.1"}}
    signature, payload_hash = crypto.sign_payload(payload)

    assert CryptoService.verify_signed_payload(
        payload=payload,
        signature_hex=signature,
        expected_hash=payload_hash,
        public_key_pem=crypto.public_key_pem,
    )
    assert not CryptoService.verify_signed_payload(
        payload={"policy": {"root": "changed"}, "release": {"version": "2026.1"}},
        signature_hex=signature,
        expected_hash=payload_hash,
        public_key_pem=crypto.public_key_pem,
    )


class _FakePostgresSession:
    def __init__(self, acquired: bool):
        self._acquired = acquired

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    async def scalar(self, *_args, **_kwargs):
        return self._acquired


def test_postgres_domain_lock_fails_fast_when_another_publisher_holds_it():
    with pytest.raises(GovernancePublicationBusyError, match="Another governed change"):
        asyncio.run(acquire_domain_governance_lock(_FakePostgresSession(False), "dom_policy"))

    asyncio.run(acquire_domain_governance_lock(_FakePostgresSession(True), "dom_policy"))


def test_api_responses_are_non_cacheable_and_set_browser_safety_headers():
    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_auditor_can_verify_a_release_from_its_stored_bundle(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GOVERNANCE_PRIVATE_KEY", _signing_key())
    monkeypatch.setenv("GOVERNANCE_KEY_ID", "test-governance-key-2026")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'release_integrity.db'}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    policy_payload = {
        "root": {
            "id": "rule_one",
            "label": "Active status",
            "target": "status.active",
            "condition": "==",
            "value": True,
            "source_citation": "Policy source section 1",
        }
    }
    rule_graph = compile_release_to_graph("rel_integrity", policy_payload)
    source_manifest, source_manifest_hash = build_policy_source_manifest(policy_payload)
    signature_payload = {
        "policy": policy_payload,
        "release": {
            "id": "rel_integrity",
            "domain_id": "dom_curr_2026",
            "version": "2026.1",
            "rule_graph_id": rule_graph.id,
            "effective_from": "2026-01-01",
            "effective_until": None,
            "applicability": {},
            "source_manifest_hash": source_manifest_hash,
        },
        "source_manifest": source_manifest,
    }
    crypto = CryptoService()
    signature, payload_hash = crypto.sign_payload(signature_payload)

    async def _prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            await ReleaseRepository(session).create_release(
                Release(
                    id="rel_integrity",
                    domain_id="dom_curr_2026",
                    version="2026.1",
                    rule_graph_id=rule_graph.id,
                    digital_signature=signature,
                    signed_payload=signature_payload,
                    signed_payload_hash=payload_hash,
                    signing_key_id=crypto.key_id,
                    signing_public_key=crypto.public_key_pem,
                    effective_from=date(2026, 1, 1),
                    source_manifest_hash=source_manifest_hash,
                ),
                rule_graph,
                policy_payload["root"],
            )

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    asyncio.run(_prepare())
    app.dependency_overrides[get_current_user] = lambda: UserIdentity(
        tenant_id="tenant_demo_uni",
        role=Role.AUDITOR,
        user_id="auditor_1",
        domain_ids=["dom_curr_2026"],
    )
    app.dependency_overrides[get_db_session] = _test_db_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/governance/releases/dom_curr_2026/2026.1/integrity")
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert response.status_code == 200
    assert response.json()["signature_valid"] is True
    assert response.json()["signing_key_id"] == "test-governance-key-2026"
