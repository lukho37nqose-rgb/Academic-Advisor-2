from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from tools.production_preflight import Status, main, run_preflight


@pytest.fixture
def signing_key() -> str:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return base64.b64encode(pem).decode("ascii")


def _set_institutional_config(monkeypatch: pytest.MonkeyPatch, signing_key: str) -> None:
    monkeypatch.setenv("IRE_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://ire_app:secret@db.institution.ac.za:5432/cacisa")
    monkeypatch.setenv("IRE_AUTO_CREATE_SCHEMA", "false")
    monkeypatch.setenv("JWT_JWKS_URL", "https://idp.institution.ac.za/.well-known/jwks.json")
    monkeypatch.setenv("JWT_ISSUER", "https://idp.institution.ac.za/")
    monkeypatch.setenv("JWT_AUDIENCE", "cacisa-nonprod-api")
    monkeypatch.setenv("IRE_TENANT_CLAIM", "tenant_id")
    monkeypatch.setenv("IRE_ROLE_CLAIM", "cacisa_role")
    monkeypatch.setenv("IRE_SUBJECT_ID_CLAIM", "student_number")
    monkeypatch.setenv("IRE_DOMAIN_IDS_CLAIM", "cacisa_domain_ids")
    monkeypatch.setenv("IRE_ALLOWED_HOSTS", "api.cacisa-nonprod.institution.ac.za")
    monkeypatch.setenv("IRE_CORS_ALLOWED_ORIGINS", "https://cacisa-nonprod.institution.ac.za")
    monkeypatch.setenv("GOVERNANCE_PRIVATE_KEY", signing_key)
    monkeypatch.setenv("GOVERNANCE_KEY_ID", "institution-nonprod-governance-2026")
    monkeypatch.setenv("REDIS_URL", "rediss://cache.institution.ac.za:6380/0")
    monkeypatch.setenv("PUBLIC_RATE_LIMIT_SALT", "institution-owned-rate-limit-salt")
    monkeypatch.setenv("S3_BUCKET_NAME", "institution-cacisa-nonprod-private")
    monkeypatch.setenv("S3_SERVER_SIDE_ENCRYPTION", "aws:kms")
    monkeypatch.setenv("REASONING_ENGINE_AI_PROVIDER", "mock")


def test_preflight_accepts_institutional_configuration(monkeypatch: pytest.MonkeyPatch, signing_key: str) -> None:
    _set_institutional_config(monkeypatch, signing_key)

    checks = run_preflight({"core", "public-assistance", "idempotent-writes", "source-intake"})

    assert all(check.status == Status.PASS for check in checks)


def test_preflight_rejects_placeholder_oidc(monkeypatch: pytest.MonkeyPatch, signing_key: str) -> None:
    _set_institutional_config(monkeypatch, signing_key)
    monkeypatch.setenv("JWT_JWKS_URL", "https://identity.example.test/.well-known/jwks.json")

    checks = run_preflight({"core"})

    assert any(check.name == "JWT_JWKS_URL" and check.status == Status.FAIL for check in checks)


def test_preflight_only_requires_optional_dependencies_when_selected(
    monkeypatch: pytest.MonkeyPatch,
    signing_key: str,
) -> None:
    _set_institutional_config(monkeypatch, signing_key)
    monkeypatch.delenv("REDIS_URL")
    monkeypatch.delenv("S3_BUCKET_NAME")

    core_checks = run_preflight({"core"})
    capability_checks = run_preflight({"core", "source-intake", "public-assistance"})

    assert all(check.status == Status.PASS for check in core_checks)
    assert any(check.name == "REDIS_URL" and check.status == Status.FAIL for check in capability_checks)
    assert any(check.name == "S3_BUCKET_NAME" and check.status == Status.FAIL for check in capability_checks)


def test_preflight_output_does_not_print_secret_values(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    signing_key: str,
) -> None:
    _set_institutional_config(monkeypatch, signing_key)
    secret_fragments = ["ire_app:secret", signing_key, "institution-owned-rate-limit-salt"]

    exit_code = main(["--capability", "core", "--capability", "public-assistance", "--capability", "source-intake"])

    captured = capsys.readouterr()
    assert exit_code == 0
    for fragment in secret_fragments:
        assert fragment not in captured.out
