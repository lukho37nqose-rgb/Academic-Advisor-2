"""Controls for any optional external AI processing of institutional data."""

import os


_SUPPORTED_PROVIDERS = {"mock", "openai"}


def configured_ai_provider() -> str:
    provider = os.environ.get("REASONING_ENGINE_AI_PROVIDER", "mock").strip().lower() or "mock"
    if provider not in _SUPPORTED_PROVIDERS:
        raise RuntimeError(
            "REASONING_ENGINE_AI_PROVIDER must be one of: "
            + ", ".join(sorted(_SUPPORTED_PROVIDERS))
            + "."
        )
    return provider


def external_ai_processing_enabled() -> bool:
    return configured_ai_provider() != "mock"


def external_ai_max_input_bytes() -> int:
    raw_value = os.environ.get("EXTERNAL_AI_MAX_INPUT_BYTES", "200000")
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError("EXTERNAL_AI_MAX_INPUT_BYTES must be a positive integer.") from exc
    if value < 1:
        raise RuntimeError("EXTERNAL_AI_MAX_INPUT_BYTES must be a positive integer.")
    return value


def validate_external_ai_processing_configuration() -> None:
    """Require an explicit institutional decision before data leaves the boundary."""
    if not external_ai_processing_enabled():
        return
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("External AI processing requires OPENAI_API_KEY.")
    if os.environ.get("IRE_ENV", "development").lower() != "production":
        return
    if os.environ.get("IRE_ALLOW_EXTERNAL_AI_PROCESSING", "false").lower() != "true":
        raise RuntimeError(
            "Production external AI processing requires IRE_ALLOW_EXTERNAL_AI_PROCESSING=true."
        )
    approval_reference = os.environ.get("IRE_EXTERNAL_AI_APPROVAL_REFERENCE", "").strip()
    if len(approval_reference) < 8:
        raise RuntimeError(
            "Production external AI processing requires an institution-owned "
            "IRE_EXTERNAL_AI_APPROVAL_REFERENCE."
        )
    external_ai_max_input_bytes()
