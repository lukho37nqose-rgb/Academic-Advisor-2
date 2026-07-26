"""
Structured Telemetry and Logging.

Enterprise software requires structured JSON logs tied to specific trace IDs
to ensure observability across distributed systems.
"""

import json
import logging
from contextvars import ContextVar, Token
from typing import Any, Mapping

# Basic setup for demo purposes.
logger = logging.getLogger("reasoning_engine")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(message)s')
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)


_request_id: ContextVar[str | None] = ContextVar("ire_request_id", default=None)
_SENSITIVE_FIELD_FRAGMENTS = (
    "authorization",
    "cookie",
    "token",
    "secret",
    "password",
    "private_key",
    "evidence",
    "content",
    "message",
    "contact",
    "email",
    "phone",
    "address",
)


def _safe_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Redact sensitive values even if a future caller logs the wrong object."""
    safe: dict[str, Any] = {}
    for key, value in fields.items():
        normalized_key = str(key).lower()
        if any(fragment in normalized_key for fragment in _SENSITIVE_FIELD_FRAGMENTS):
            safe[str(key)] = "[REDACTED]"
        elif isinstance(value, (str, int, float, bool)) or value is None:
            safe[str(key)] = value if not isinstance(value, str) else value[:256]
        else:
            safe[str(key)] = "[OMITTED]"
    return safe


def set_request_id(request_id: str) -> Token[str | None]:
    """Bind a correlation identifier to the current async request context."""
    return _request_id.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Clear request context after the request has completed."""
    _request_id.reset(token)


def current_request_id() -> str | None:
    """Return the request correlation identifier, when execution has one."""
    return _request_id.get()

class Telemetry:
    @staticmethod
    def log_event(event_name: str, **kwargs: Any) -> None:
        """
        Emits a structured JSON log.
        In production, this routes to Datadog, ELK, or CloudWatch.
        """
        log_payload = {"event": event_name, **_safe_fields(kwargs)}
        request_id = current_request_id()
        if request_id:
            log_payload["request_id"] = request_id
        # In a real app, we would inject the current trace_id via contextvars
        logger.info(json.dumps(log_payload))

    @staticmethod
    def log_error(error: Exception, context: Mapping[str, Any]) -> None:
        """Emits a structured error log."""
        log_payload = {
            "event": "system_error",
            "error_type": type(error).__name__,
            "context": _safe_fields(context),
        }
        request_id = current_request_id()
        if request_id:
            log_payload["request_id"] = request_id
        logger.error(json.dumps(log_payload))
