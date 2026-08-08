"""Static production configuration preflight for institutional rehearsals.

The preflight is intentionally non-networked. It validates whether the runtime
configuration is structurally safe to attempt a deployment rehearsal, without
printing secrets or claiming that external services are reachable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Iterable
from urllib.parse import urlsplit

from app.core.crypto import CryptoService
from app.services.ai_safety import validate_external_ai_processing_configuration
from app.services.http_safety import allowed_hosts, cors_origins


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    detail: str


_PLACEHOLDER_FRAGMENTS = (
    "example.test",
    "example.org",
    "example.edu",
    "your-",
    "change-me",
    "placeholder",
    "tenant.auth0.com",
)


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(fragment in lowered for fragment in _PLACEHOLDER_FRAGMENTS)


def _require(name: str, *, allow_placeholder: bool = False) -> Check:
    value = _env(name)
    if not value:
        return Check(name, Status.FAIL, f"{name} is required.")
    if not allow_placeholder and _is_placeholder(value):
        return Check(name, Status.FAIL, f"{name} must be institution-specific, not a placeholder/test value.")
    return Check(name, Status.PASS, f"{name} is present.")


def _https_url(name: str, *, allow_placeholder: bool = False) -> Check:
    value = _env(name)
    if not value:
        return Check(name, Status.FAIL, f"{name} is required.")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return Check(name, Status.FAIL, f"{name} must be a credential-free HTTPS URL.")
    if not allow_placeholder and _is_placeholder(value):
        return Check(name, Status.FAIL, f"{name} must be institution-specific, not a placeholder/test URL.")
    return Check(name, Status.PASS, f"{name} is a credential-free HTTPS URL.")


def _database_url() -> Check:
    value = _env("DATABASE_URL")
    if not value:
        return Check("DATABASE_URL", Status.FAIL, "DATABASE_URL is required.")
    if not value.startswith("postgresql+asyncpg://"):
        return Check("DATABASE_URL", Status.FAIL, "DATABASE_URL must use postgresql+asyncpg; SQLite is not permitted.")
    if _is_placeholder(value):
        return Check("DATABASE_URL", Status.FAIL, "DATABASE_URL must be institution-specific, not a placeholder.")
    return Check("DATABASE_URL", Status.PASS, "DATABASE_URL uses the PostgreSQL async driver.")


def _auto_schema() -> Check:
    if _env("IRE_AUTO_CREATE_SCHEMA").lower() == "true":
        return Check("IRE_AUTO_CREATE_SCHEMA", Status.FAIL, "Application replicas must not run migrations at startup.")
    return Check("IRE_AUTO_CREATE_SCHEMA", Status.PASS, "Application startup schema creation is disabled.")


def _signing_key() -> Check:
    if not _env("GOVERNANCE_PRIVATE_KEY"):
        return Check("GOVERNANCE_PRIVATE_KEY", Status.FAIL, "GOVERNANCE_PRIVATE_KEY is required.")
    try:
        CryptoService()
    except ValueError:
        return Check("GOVERNANCE_PRIVATE_KEY", Status.FAIL, "GOVERNANCE_PRIVATE_KEY must contain a usable private signing key.")
    return Check("GOVERNANCE_PRIVATE_KEY", Status.PASS, "Governance signing key parses successfully.")


def _http_boundaries() -> list[Check]:
    checks: list[Check] = []
    try:
        allowed_hosts()
        checks.append(Check("IRE_ALLOWED_HOSTS", Status.PASS, "Allowed hosts are explicit and non-wildcard."))
    except RuntimeError as exc:
        checks.append(Check("IRE_ALLOWED_HOSTS", Status.FAIL, str(exc)))
    try:
        cors_origins()
        checks.append(Check("IRE_CORS_ALLOWED_ORIGINS", Status.PASS, "CORS origins are explicit HTTPS origins."))
    except RuntimeError as exc:
        checks.append(Check("IRE_CORS_ALLOWED_ORIGINS", Status.FAIL, str(exc)))
    return checks


def _redis() -> list[Check]:
    checks = [_require("REDIS_URL"), _require("PUBLIC_RATE_LIMIT_SALT")]
    value = _env("REDIS_URL")
    if value:
        scheme = urlsplit(value).scheme
        checks.append(
            Check(
                "REDIS_URL_SCHEME",
                Status.PASS if scheme == "rediss" else Status.FAIL,
                "REDIS_URL uses encrypted rediss transport." if scheme == "rediss" else "REDIS_URL must use rediss:// in production.",
            )
        )
    salt = _env("PUBLIC_RATE_LIMIT_SALT")
    if salt:
        checks.append(
            Check(
                "PUBLIC_RATE_LIMIT_SALT_STRENGTH",
                Status.PASS if len(salt) >= 16 and not _is_placeholder(salt) else Status.FAIL,
                "Rate-limit salt is non-placeholder." if len(salt) >= 16 and not _is_placeholder(salt) else "PUBLIC_RATE_LIMIT_SALT must be non-placeholder and at least 16 characters.",
            )
        )
    return checks


def _object_storage() -> list[Check]:
    checks = [_require("S3_BUCKET_NAME"), _require("S3_SERVER_SIDE_ENCRYPTION", allow_placeholder=True)]
    algorithm = _env("S3_SERVER_SIDE_ENCRYPTION")
    if algorithm:
        checks.append(
            Check(
                "S3_SERVER_SIDE_ENCRYPTION_VALUE",
                Status.PASS if algorithm in {"AES256", "aws:kms"} else Status.FAIL,
                "Object-store encryption setting is recognised." if algorithm in {"AES256", "aws:kms"} else "S3_SERVER_SIDE_ENCRYPTION must be AES256 or aws:kms.",
            )
        )
    return checks


def _claim_mapping() -> list[Check]:
    return [
        _require("IRE_TENANT_CLAIM"),
        _require("IRE_ROLE_CLAIM"),
        _require("IRE_SUBJECT_ID_CLAIM"),
        _require("IRE_DOMAIN_IDS_CLAIM"),
    ]


def _external_ai() -> Check:
    try:
        validate_external_ai_processing_configuration()
    except RuntimeError as exc:
        return Check("EXTERNAL_AI_PROCESSING", Status.FAIL, str(exc))
    return Check("EXTERNAL_AI_PROCESSING", Status.PASS, "External AI configuration is fail-closed or explicitly approved.")


def _capabilities(values: Iterable[str]) -> set[str]:
    capabilities = {value.strip().lower() for value in values if value.strip()}
    if not capabilities:
        capabilities = {
            value.strip().lower()
            for value in _env("IRE_PRODUCTION_CAPABILITIES").split(",")
            if value.strip()
        }
    return capabilities or {"core", "public-assistance", "idempotent-writes", "source-intake"}


def run_preflight(capabilities: set[str]) -> list[Check]:
    checks = [
        Check(
            "IRE_ENV",
            Status.PASS if _env("IRE_ENV").lower() == "production" else Status.FAIL,
            "IRE_ENV is production." if _env("IRE_ENV").lower() == "production" else "IRE_ENV must be set to production.",
        ),
        _database_url(),
        _auto_schema(),
        _https_url("JWT_JWKS_URL"),
        _https_url("JWT_ISSUER"),
        _require("JWT_AUDIENCE"),
        *_claim_mapping(),
        *_http_boundaries(),
        _signing_key(),
        _require("GOVERNANCE_KEY_ID"),
        _external_ai(),
    ]

    if capabilities & {"public-assistance", "idempotent-writes"}:
        checks.extend(_redis())
    if capabilities & {"source-intake", "direct-handbook-uploads"}:
        checks.extend(_object_storage())
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate static production configuration without printing secrets.")
    parser.add_argument(
        "--capability",
        action="append",
        default=[],
        help="Capability to validate. Defaults to core plus currently enabled pilot capabilities.",
    )
    parser.add_argument("--json", action="store_true", help="Emit a JSON report.")
    args = parser.parse_args(argv)

    capabilities = _capabilities(args.capability)
    checks = run_preflight(capabilities)
    ok = all(check.status == Status.PASS for check in checks)
    report = {
        "ready": ok,
        "mode": "static-configuration",
        "capabilities": sorted(capabilities),
        "checks": [asdict(check) for check in checks],
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Production preflight: {'PASS' if ok else 'FAIL'}")
        print(f"Mode: {report['mode']}")
        print(f"Capabilities: {', '.join(report['capabilities'])}")
        for check in checks:
            print(f"[{check.status.value.upper()}] {check.name}: {check.detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
