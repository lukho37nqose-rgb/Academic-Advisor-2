"""Request and worker tenant context applied to PostgreSQL RLS transactions."""

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator
import os


_tenant_id: ContextVar[str | None] = ContextVar("ire_tenant_id", default=None)
_access_mode: ContextVar[str] = ContextVar("ire_access_mode", default="none")
_public_support_request_id: ContextVar[str | None] = ContextVar(
    "ire_public_support_request_id", default=None
)


def current_tenant_id() -> str | None:
    return _tenant_id.get()


def current_access_mode() -> str:
    return _access_mode.get()


def current_public_support_request_id() -> str | None:
    """Returns the server-generated public request allowed in this transaction."""
    return _public_support_request_id.get()


def begin_request_scope(*, public: bool) -> tuple[Token[str | None], Token[str], Token[str | None]]:
    """Clears inherited task context before handling a new HTTP request."""
    return (
        _tenant_id.set(None),
        _access_mode.set("public" if public else "tenant"),
        _public_support_request_id.set(None),
    )


def reset_request_scope(tokens: tuple[Token[str | None], Token[str], Token[str | None]]) -> None:
    tenant_token, access_token, public_request_token = tokens
    _tenant_id.reset(tenant_token)
    _access_mode.reset(access_token)
    _public_support_request_id.reset(public_request_token)


def bind_authenticated_tenant(tenant_id: str) -> None:
    if not tenant_id:
        raise ValueError("Tenant identifier cannot be blank.")
    _tenant_id.set(tenant_id)
    _access_mode.set("tenant")
    _public_support_request_id.set(None)


def bind_provider_access() -> None:
    """Mark a request as provider-control-plane work, never as tenant access."""
    _tenant_id.set(None)
    _access_mode.set("provider")
    _public_support_request_id.set(None)


@contextmanager
def public_support_request_scope(request_id: str) -> Iterator[None]:
    """Limits public writes to the one server-generated assistance request."""
    if current_access_mode() != "public":
        raise ValueError("Public support request scope requires a public request context.")
    if not request_id:
        raise ValueError("Public support request identifier cannot be blank.")
    request_token = _public_support_request_id.set(request_id)
    try:
        yield
    finally:
        _public_support_request_id.reset(request_token)


@contextmanager
def tenant_scope(tenant_id: str) -> Iterator[None]:
    """Scopes a background task to one tenant for every transaction it opens."""
    if not tenant_id:
        raise ValueError("Background work requires an explicit tenant identifier.")
    tenant_token = _tenant_id.set(tenant_id)
    access_token = _access_mode.set("tenant")
    public_request_token = _public_support_request_id.set(None)
    try:
        yield
    finally:
        _tenant_id.reset(tenant_token)
        _access_mode.reset(access_token)
        _public_support_request_id.reset(public_request_token)


def production_background_scope_required() -> bool:
    """Background work must name its tenant when production RLS is active."""
    return (
        os.environ.get("IRE_ENV", "development").lower() == "production"
        and os.environ.get("DATABASE_URL", "").startswith("postgresql+")
    )


def configured_retention_tenant_ids() -> tuple[str, ...]:
    values = tuple(
        value.strip()
        for value in os.environ.get("IRE_RETENTION_TENANT_IDS", "").split(",")
        if value.strip()
    )
    if production_background_scope_required() and not values:
        raise RuntimeError(
            "Production retention work requires IRE_RETENTION_TENANT_IDS so it can run under tenant RLS."
        )
    return values
