"""Fail-closed checks for a production Institutional Reasoning Engine deployment."""

import os

from app.core.crypto import CryptoService
from app.services.access_controls import validate_production_access_configuration
from app.services.http_safety import allowed_hosts, cors_origins
from app.services.ai_safety import validate_external_ai_processing_configuration


def _is_production() -> bool:
    return os.environ.get("IRE_ENV", "development").lower() == "production"


def validate_production_readiness() -> None:
    """Reject startup when required production controls are absent or unsafe.

    These checks intentionally validate configuration only. Connectivity, secret
    rotation, backups, and institutional approval are operational release gates
    documented in ``docs/PRODUCTION_DEPLOYMENT.md``.
    """
    if not _is_production():
        return

    validate_production_access_configuration()
    validate_external_ai_processing_configuration()
    allowed_hosts()
    cors_origins()

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.startswith("postgresql+asyncpg://"):
        raise RuntimeError("Production requires DATABASE_URL to use postgresql+asyncpg; SQLite is not permitted.")

    if os.environ.get("IRE_AUTO_CREATE_SCHEMA", "false").lower() == "true":
        raise RuntimeError("IRE_AUTO_CREATE_SCHEMA must remain false in production; deploy reviewed Alembic migrations separately.")

    required = [
        "S3_BUCKET_NAME",
        "S3_SERVER_SIDE_ENCRYPTION",
        "GOVERNANCE_PRIVATE_KEY",
        "GOVERNANCE_KEY_ID",
    ]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Production release integrity requires: {', '.join(missing)}.")

    try:
        CryptoService()
    except ValueError as exc:
        raise RuntimeError("GOVERNANCE_PRIVATE_KEY must contain a usable private signing key in production.") from exc
