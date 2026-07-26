import time

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.services.auth import (
    Role,
    UserIdentity,
    ensure_subject_access,
    get_current_user,
    validate_production_oidc_configuration,
)


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_development_hs256_token_maps_ire_identity_claims(monkeypatch):
    secret = "development-secret-that-is-long-enough-for-hs256"
    monkeypatch.setenv("IRE_ENV", "development")
    monkeypatch.setenv("JWT_SECRET_KEY", secret)
    monkeypatch.delenv("JWT_JWKS_URL", raising=False)
    token = jwt.encode(
        {
            "sub": "user_1",
            "tenant_id": "tenant_1",
            "role": "metadata_steward",
            "domain_ids": ["dom_1"],
            "exp": int(time.time()) + 300,
        },
        secret,
        algorithm="HS256",
    )

    identity = get_current_user(_credentials(token))

    assert identity.user_id == "user_1"
    assert identity.tenant_id == "tenant_1"
    assert identity.role == Role.METADATA_STEWARD
    assert identity.subject_id == "user_1"
    assert identity.domain_ids == ["dom_1"]


def test_subject_identity_claim_prevents_cross_subject_access(monkeypatch):
    monkeypatch.setenv("IRE_SUBJECT_ID_CLAIM", "student_number")
    subject = UserIdentity(
        tenant_id="tenant_1",
        role=Role.SUBJECT,
        user_id="identity_1",
        subject_id="student_123",
        domain_ids=["dom_1"],
    )

    ensure_subject_access(subject, "student_123")
    with pytest.raises(HTTPException) as error:
        ensure_subject_access(subject, "student_456")

    assert error.value.status_code == 403


def test_staff_token_does_not_need_the_subject_claim(monkeypatch):
    secret = "development-secret-that-is-long-enough-for-hs256"
    monkeypatch.setenv("IRE_ENV", "development")
    monkeypatch.setenv("JWT_SECRET_KEY", secret)
    monkeypatch.setenv("IRE_SUBJECT_ID_CLAIM", "student_number")
    monkeypatch.delenv("JWT_JWKS_URL", raising=False)
    token = jwt.encode(
        {
            "sub": "staff_1",
            "tenant_id": "tenant_1",
            "role": "auditor",
            "domain_ids": ["dom_1"],
            "exp": int(time.time()) + 300,
        },
        secret,
        algorithm="HS256",
    )

    identity = get_current_user(_credentials(token))

    assert identity.user_id == "staff_1"
    assert identity.subject_id is None


def test_production_refuses_shared_secret_authentication(monkeypatch):
    monkeypatch.setenv("IRE_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "development-secret-that-is-long-enough-for-hs256")
    monkeypatch.delenv("JWT_JWKS_URL", raising=False)

    with pytest.raises(HTTPException) as error:
        get_current_user(_credentials("not-a-token"))

    assert error.value.status_code == 500
    assert "JWT_JWKS_URL" in error.value.detail


def test_invalid_domain_assignment_claim_is_rejected(monkeypatch):
    secret = "development-secret-that-is-long-enough-for-hs256"
    monkeypatch.setenv("IRE_ENV", "development")
    monkeypatch.setenv("JWT_SECRET_KEY", secret)
    monkeypatch.delenv("JWT_JWKS_URL", raising=False)
    token = jwt.encode(
        {
            "sub": "user_1",
            "tenant_id": "tenant_1",
            "role": "auditor",
            "domain_ids": "dom_1",
            "exp": int(time.time()) + 300,
        },
        secret,
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as error:
        get_current_user(_credentials(token))

    assert error.value.status_code == 401


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("tenant_id", ""),
        ("sub", ""),
        ("domain_ids", ["dom_1", "dom_1"]),
        ("domain_ids", [" "]),
    ],
)
def test_identity_claims_cannot_be_blank_or_ambiguous(monkeypatch, claim, value):
    secret = "development-secret-that-is-long-enough-for-hs256"
    monkeypatch.setenv("IRE_ENV", "development")
    monkeypatch.setenv("JWT_SECRET_KEY", secret)
    monkeypatch.delenv("JWT_JWKS_URL", raising=False)
    payload = {
        "sub": "user_1",
        "tenant_id": "tenant_1",
        "role": "auditor",
        "domain_ids": ["dom_1"],
        "exp": int(time.time()) + 300,
    }
    payload[claim] = value
    token = jwt.encode(payload, secret, algorithm="HS256")

    with pytest.raises(HTTPException) as error:
        get_current_user(_credentials(token))

    assert error.value.status_code == 401


def test_production_oidc_configuration_requires_https_endpoints(monkeypatch):
    monkeypatch.setenv("IRE_ENV", "production")
    monkeypatch.setenv("JWT_JWKS_URL", "http://identity.example.test/jwks")
    monkeypatch.setenv("JWT_ISSUER", "https://identity.example.test/")
    monkeypatch.setenv("JWT_AUDIENCE", "institutional-reasoning-engine")

    with pytest.raises(RuntimeError, match="JWT_JWKS_URL"):
        validate_production_oidc_configuration()
