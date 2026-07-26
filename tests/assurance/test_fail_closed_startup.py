from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.services.production_readiness import validate_production_readiness


def _signing_key() -> str:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return base64.b64encode(pem).decode("ascii")


def _set_complete_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IRE_ENV", "production")
    monkeypatch.setenv("JWT_JWKS_URL", "https://identity.example.test/.well-known/jwks.json")
    monkeypatch.setenv("JWT_ISSUER", "https://identity.example.test/")
    monkeypatch.setenv("JWT_AUDIENCE", "ire-assurance")
    monkeypatch.setenv("REDIS_URL", "rediss://cache.example.test:6380/0")
    monkeypatch.setenv("PUBLIC_RATE_LIMIT_SALT", "assurance-test-rate-limit-salt")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://ire:password@database.example.test:5432/ire")
    monkeypatch.setenv("IRE_AUTO_CREATE_SCHEMA", "false")
    monkeypatch.setenv("S3_BUCKET_NAME", "private-assurance-bucket")
    monkeypatch.setenv("S3_SERVER_SIDE_ENCRYPTION", "aws:kms")
    monkeypatch.setenv("GOVERNANCE_PRIVATE_KEY", _signing_key())
    monkeypatch.setenv("GOVERNANCE_KEY_ID", "assurance-key")
    monkeypatch.setenv("IRE_ALLOWED_HOSTS", "reasoning.example.test")
    monkeypatch.setenv("IRE_CORS_ALLOWED_ORIGINS", "https://reasoning.example.test")
    monkeypatch.setenv("REASONING_ENGINE_AI_PROVIDER", "mock")


@pytest.mark.parametrize(
    "setting,expected_message",
    [
        ("S3_BUCKET_NAME", "Production release integrity requires"),
        ("S3_SERVER_SIDE_ENCRYPTION", "Production release integrity requires"),
        ("GOVERNANCE_PRIVATE_KEY", "Production release integrity requires"),
        ("GOVERNANCE_KEY_ID", "Production release integrity requires"),
        ("IRE_ALLOWED_HOSTS", "IRE_ALLOWED_HOSTS"),
        ("IRE_CORS_ALLOWED_ORIGINS", "IRE_CORS_ALLOWED_ORIGINS"),
    ],
)
def test_production_startup_fails_when_a_required_safety_setting_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    setting: str,
    expected_message: str,
) -> None:
    _set_complete_configuration(monkeypatch)
    monkeypatch.delenv(setting, raising=False)

    with pytest.raises(RuntimeError, match=expected_message):
        validate_production_readiness()
