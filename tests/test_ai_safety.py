import pytest

from app.services.ai_safety import (
    configured_ai_provider,
    validate_external_ai_processing_configuration,
)
from app.services.llm_gateway import get_async_client


def test_mock_provider_is_the_safe_default_even_when_an_api_key_exists(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("REASONING_ENGINE_AI_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "unexpected-key-must-not-enable-processing")

    assert configured_ai_provider() == "mock"
    assert get_async_client() is None


def test_production_external_ai_requires_explicit_institutional_authorisation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("IRE_ENV", "production")
    monkeypatch.setenv("REASONING_ENGINE_AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("IRE_ALLOW_EXTERNAL_AI_PROCESSING", "false")
    monkeypatch.delenv("IRE_EXTERNAL_AI_APPROVAL_REFERENCE", raising=False)

    with pytest.raises(RuntimeError, match="IRE_ALLOW_EXTERNAL_AI_PROCESSING"):
        validate_external_ai_processing_configuration()


def test_production_external_ai_requires_an_institution_owned_approval_reference(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("IRE_ENV", "production")
    monkeypatch.setenv("REASONING_ENGINE_AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("IRE_ALLOW_EXTERNAL_AI_PROCESSING", "true")
    monkeypatch.setenv("IRE_EXTERNAL_AI_APPROVAL_REFERENCE", "short")

    with pytest.raises(RuntimeError, match="IRE_EXTERNAL_AI_APPROVAL_REFERENCE"):
        validate_external_ai_processing_configuration()
