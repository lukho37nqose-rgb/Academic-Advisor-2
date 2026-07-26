"""HTTP boundary controls for institutional and personal data."""

import os
from collections.abc import Iterable

from starlette.responses import Response


_DEV_ALLOWED_HOSTS = ("localhost", "127.0.0.1", "testserver")
_DEV_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
)


def is_production() -> bool:
    return os.environ.get("IRE_ENV", "development").lower() == "production"


def _configured_values(name: str, defaults: Iterable[str]) -> tuple[str, ...]:
    configured = os.environ.get(name, "")
    if not configured.strip():
        return tuple(defaults)
    return tuple(value.strip().lower() for value in configured.split(",") if value.strip())


def allowed_hosts() -> tuple[str, ...]:
    values = _configured_values("IRE_ALLOWED_HOSTS", _DEV_ALLOWED_HOSTS)
    if is_production() and not os.environ.get("IRE_ALLOWED_HOSTS", "").strip():
        raise RuntimeError("Production requires IRE_ALLOWED_HOSTS; wildcard host routing is not permitted.")
    if "*" in values:
        raise RuntimeError("IRE_ALLOWED_HOSTS cannot contain a wildcard.")
    return values


def cors_origins() -> tuple[str, ...]:
    values = _configured_values("IRE_CORS_ALLOWED_ORIGINS", _DEV_CORS_ORIGINS)
    if is_production() and not os.environ.get("IRE_CORS_ALLOWED_ORIGINS", "").strip():
        raise RuntimeError("Production requires IRE_CORS_ALLOWED_ORIGINS; wildcard CORS is not permitted.")
    if "*" in values:
        raise RuntimeError("IRE_CORS_ALLOWED_ORIGINS cannot contain a wildcard.")
    if is_production() and any(not value.startswith("https://") for value in values):
        raise RuntimeError("Production CORS origins must use HTTPS.")
    return values


def apply_security_headers(response: Response) -> None:
    """Prevent browsers and intermediary caches from mishandling sensitive API data."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=()"
    if is_production():
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
