import pytest

from app.services.access_controls import validate_production_access_configuration


def test_production_access_controls_fail_closed_without_required_services(monkeypatch):
    monkeypatch.setenv("IRE_ENV", "production")
    for name in [
        "JWT_JWKS_URL",
        "JWT_ISSUER",
        "JWT_AUDIENCE",
        "REDIS_URL",
        "PUBLIC_RATE_LIMIT_SALT",
    ]:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError) as error:
        validate_production_access_configuration()

    assert "JWT_JWKS_URL" in str(error.value)
