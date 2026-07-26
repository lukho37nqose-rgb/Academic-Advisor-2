import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.api import app
from app.services.production_readiness import validate_production_readiness


@pytest.fixture
def signing_key() -> str:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return base64.b64encode(pem).decode("ascii")


def _set_valid_production_configuration(monkeypatch: pytest.MonkeyPatch, signing_key: str) -> None:
    monkeypatch.setenv("IRE_ENV", "production")
    monkeypatch.setenv("JWT_JWKS_URL", "https://identity.example.test/.well-known/jwks.json")
    monkeypatch.setenv("JWT_ISSUER", "https://identity.example.test/")
    monkeypatch.setenv("JWT_AUDIENCE", "institutional-reasoning-engine")
    monkeypatch.setenv("REDIS_URL", "rediss://cache.example.test:6380/0")
    monkeypatch.setenv("PUBLIC_RATE_LIMIT_SALT", "a-long-non-placeholder-rate-limit-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://ire:password@database.example.test:5432/ire")
    monkeypatch.setenv("IRE_AUTO_CREATE_SCHEMA", "false")
    monkeypatch.setenv("S3_BUCKET_NAME", "ire-uct-pilot-source-documents")
    monkeypatch.setenv("S3_SERVER_SIDE_ENCRYPTION", "aws:kms")
    monkeypatch.setenv("GOVERNANCE_PRIVATE_KEY", signing_key)
    monkeypatch.setenv("GOVERNANCE_KEY_ID", "institution-governance-key-2026")
    monkeypatch.setenv("IRE_ALLOWED_HOSTS", "reasoning.example.test")
    monkeypatch.setenv("IRE_CORS_ALLOWED_ORIGINS", "https://reasoning.example.test")
    monkeypatch.setenv("REASONING_ENGINE_AI_PROVIDER", "mock")


def test_production_readiness_rejects_sqlite(monkeypatch: pytest.MonkeyPatch, signing_key: str):
    _set_valid_production_configuration(monkeypatch, signing_key)
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./reasoning_engine.db")

    with pytest.raises(RuntimeError, match="postgresql\\+asyncpg"):
        validate_production_readiness()


def test_production_readiness_rejects_automatic_schema_creation(monkeypatch: pytest.MonkeyPatch, signing_key: str):
    _set_valid_production_configuration(monkeypatch, signing_key)
    monkeypatch.setenv("IRE_AUTO_CREATE_SCHEMA", "true")

    with pytest.raises(RuntimeError, match="IRE_AUTO_CREATE_SCHEMA"):
        validate_production_readiness()


def test_production_readiness_requires_usable_signing_key(monkeypatch: pytest.MonkeyPatch, signing_key: str):
    _set_valid_production_configuration(monkeypatch, signing_key)
    monkeypatch.setenv("GOVERNANCE_PRIVATE_KEY", "not-a-signing-key")

    with pytest.raises(RuntimeError, match="usable private signing key"):
        validate_production_readiness()


def test_production_readiness_rejects_wildcard_cors(monkeypatch: pytest.MonkeyPatch, signing_key: str):
    _set_valid_production_configuration(monkeypatch, signing_key)
    monkeypatch.setenv("IRE_CORS_ALLOWED_ORIGINS", "*")

    with pytest.raises(RuntimeError, match="wildcard"):
        validate_production_readiness()


def test_production_readiness_rejects_unencrypted_redis(monkeypatch: pytest.MonkeyPatch, signing_key: str):
    _set_valid_production_configuration(monkeypatch, signing_key)
    monkeypatch.setenv("REDIS_URL", "redis://cache.example.test:6379/0")

    with pytest.raises(RuntimeError, match="rediss"):
        validate_production_readiness()


def test_production_readiness_accepts_complete_configuration(monkeypatch: pytest.MonkeyPatch, signing_key: str):
    _set_valid_production_configuration(monkeypatch, signing_key)

    validate_production_readiness()


def test_application_startup_enforces_production_readiness(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("IRE_ENV", "production")
    for name in [
        "JWT_JWKS_URL",
        "JWT_ISSUER",
        "JWT_AUDIENCE",
        "REDIS_URL",
        "PUBLIC_RATE_LIMIT_SALT",
    ]:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="JWT_JWKS_URL"):
        with TestClient(app):
            pass
