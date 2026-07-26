"""Operational controls for public access and human-assistance records."""

import hashlib
import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status

from app.infrastructure.idempotency import redis_client


def _positive_int(name: str, default: int, maximum: int) -> int:
    raw_value = os.environ.get(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a whole number.") from exc
    if value < 1 or value > maximum:
        raise RuntimeError(f"{name} must be between 1 and {maximum}.")
    return value


def support_request_retention_days() -> int:
    return _positive_int("SUPPORT_REQUEST_RETENTION_DAYS", 90, 3650)


def decision_review_retention_days() -> int:
    """Retention for personal decision-review records after a case is closed."""
    return _positive_int("DECISION_REVIEW_RETENTION_DAYS", 365, 3650)


def support_response_target_hours(access_settings: dict[str, object]) -> int | None:
    value = access_settings.get("support_response_target_hours")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > 24 * 365:
        return None
    return value


def response_due_at(access_settings: dict[str, object]) -> datetime | None:
    target_hours = support_response_target_hours(access_settings)
    return datetime.now(timezone.utc) + timedelta(hours=target_hours) if target_hours else None


def decision_review_response_due_at(access_settings: dict[str, object]) -> datetime | None:
    value = access_settings.get("decision_review_response_target_hours")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > 24 * 365:
        return None
    return datetime.now(timezone.utc) + timedelta(hours=value)


def public_client_fingerprint(request: Request) -> str:
    """Creates a non-reversible key without storing a raw IP address."""
    client_address = request.client.host if request.client else "unknown"
    if os.environ.get("IRE_TRUST_PROXY_HEADERS", "false").lower() == "true":
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            client_address = forwarded_for.split(",", 1)[0].strip()
    salt = os.environ.get("PUBLIC_RATE_LIMIT_SALT", "local-development-rate-limit-salt")
    return hashlib.sha256(f"{salt}:{client_address}".encode("utf-8")).hexdigest()


async def enforce_public_support_rate_limit(request: Request, domain_id: str) -> None:
    """Applies a Redis fixed-window limit before a public form reaches storage."""
    maximum = _positive_int("PUBLIC_SUPPORT_RATE_LIMIT_MAX", 5, 1000)
    window_seconds = _positive_int("PUBLIC_SUPPORT_RATE_LIMIT_WINDOW_SECONDS", 3600, 86400)
    fingerprint = public_client_fingerprint(request)
    key = f"public_support:{domain_id}:{fingerprint}"
    try:
        request_count = await redis_client.incr(key)
        if request_count == 1:
            await redis_client.expire(key, window_seconds)
        if request_count > maximum:
            retry_after = await redis_client.ttl(key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many assistance requests from this connection. Please try again later.",
                headers={"Retry-After": str(max(1, retry_after))},
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The assistance service is temporarily unavailable. Please use the offline contact route.",
        ) from exc


def validate_production_access_configuration() -> None:
    """Fails closed when production lacks the services that protect public access."""
    if os.environ.get("IRE_ENV", "development").lower() != "production":
        return
    required = ["JWT_JWKS_URL", "JWT_ISSUER", "JWT_AUDIENCE", "REDIS_URL", "PUBLIC_RATE_LIMIT_SALT"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Production access controls require: {', '.join(missing)}.")
    rate_limit_salt = os.environ["PUBLIC_RATE_LIMIT_SALT"]
    if len(rate_limit_salt) < 16 or rate_limit_salt.startswith("change-me"):
        raise RuntimeError("PUBLIC_RATE_LIMIT_SALT must be a non-placeholder secret of at least 16 characters.")
    _positive_int("PUBLIC_SUPPORT_RATE_LIMIT_MAX", 5, 1000)
    _positive_int("PUBLIC_SUPPORT_RATE_LIMIT_WINDOW_SECONDS", 3600, 86400)
    support_request_retention_days()
    decision_review_retention_days()
