"""Run a disposable production-mode application container rehearsal."""

from __future__ import annotations

import argparse
import asyncio
import base64
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import unquote, urlsplit

import asyncpg
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_NAME = "ire_production_rehearsal"
DEFAULT_PORT = "5434"
DEFAULT_BOOTSTRAP_URL = f"postgresql+asyncpg://postgres:postgres@127.0.0.1:{DEFAULT_PORT}/{DATABASE_NAME}"
DEFAULT_MIGRATOR_URL = (
    f"postgresql+asyncpg://ire_prod_migrator_rehearsal:migrator-rehearsal-password"
    f"@127.0.0.1:{DEFAULT_PORT}/{DATABASE_NAME}"
)
DEFAULT_APP_URL = (
    f"postgresql+asyncpg://ire_prod_app_rehearsal:app-rehearsal-password"
    f"@127.0.0.1:{DEFAULT_PORT}/{DATABASE_NAME}"
)
ROLE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,62}_rehearsal$")


@dataclass(frozen=True)
class Configuration:
    bootstrap_url: str
    migrator_url: str
    app_url: str
    database_name: str
    migrator_role: str
    migrator_password: str
    app_role: str
    app_password: str


def _run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
    display_command: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(display_command or command), flush=True)
    return subprocess.run(command, cwd=PROJECT_ROOT, env=env, text=True, check=True, timeout=timeout)


def _docker() -> str:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("Docker is required for the production-stack rehearsal but was not found on PATH.")
    return docker


def _asyncpg_url(sqlalchemy_url: str) -> str:
    return sqlalchemy_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _wait_for_database(url: str, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            connection = await asyncpg.connect(_asyncpg_url(url))
            await connection.close()
            return
        except (OSError, asyncpg.PostgresError) as error:
            last_error = error
            await asyncio.sleep(1)
    raise RuntimeError(f"PostgreSQL did not become ready within {timeout_seconds}s: {last_error}")


def _url_identity(url: str, setting_name: str) -> tuple[str, str, str]:
    parsed = urlsplit(url)
    if parsed.scheme != "postgresql+asyncpg" or not parsed.hostname:
        raise RuntimeError(f"{setting_name} must be a postgresql+asyncpg URL.")
    database_name = unquote(parsed.path.lstrip("/"))
    role = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    if not database_name or not role or not password:
        raise RuntimeError(f"{setting_name} must include a database, role, and password.")
    return database_name, role, password


def _quote_identifier(value: str) -> str:
    if not ROLE_PATTERN.fullmatch(value):
        raise RuntimeError("Production rehearsal roles must end in '_rehearsal' and use lowercase SQL identifiers.")
    return f'"{value}"'


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _configuration() -> Configuration:
    if os.environ.get("IRE_PRODUCTION_REHEARSAL_ALLOW_DESTRUCTIVE") != "confirmed":
        raise RuntimeError("Set IRE_PRODUCTION_REHEARSAL_ALLOW_DESTRUCTIVE=confirmed for the dedicated rehearsal database.")
    bootstrap_url = os.environ.get("IRE_PRODUCTION_REHEARSAL_BOOTSTRAP_URL", DEFAULT_BOOTSTRAP_URL)
    migrator_url = os.environ.get("IRE_PRODUCTION_REHEARSAL_MIGRATOR_URL", DEFAULT_MIGRATOR_URL)
    app_url = os.environ.get("IRE_PRODUCTION_REHEARSAL_APP_URL", DEFAULT_APP_URL)
    bootstrap_database, _bootstrap_role, _bootstrap_password = _url_identity(bootstrap_url, "IRE_PRODUCTION_REHEARSAL_BOOTSTRAP_URL")
    migrator_database, migrator_role, migrator_password = _url_identity(migrator_url, "IRE_PRODUCTION_REHEARSAL_MIGRATOR_URL")
    app_database, app_role, app_password = _url_identity(app_url, "IRE_PRODUCTION_REHEARSAL_APP_URL")
    if {bootstrap_database, migrator_database, app_database} != {DATABASE_NAME}:
        raise RuntimeError(f"Production rehearsal may only target the dedicated {DATABASE_NAME} database.")
    if migrator_role == app_role:
        raise RuntimeError("Production rehearsal requires distinct migration and serving roles.")
    _quote_identifier(migrator_role)
    _quote_identifier(app_role)
    return Configuration(
        bootstrap_url=bootstrap_url,
        migrator_url=migrator_url,
        app_url=app_url,
        database_name=bootstrap_database,
        migrator_role=migrator_role,
        migrator_password=migrator_password,
        app_role=app_role,
        app_password=app_password,
    )


async def _bootstrap_database(configuration: Configuration) -> None:
    bootstrap_engine = create_async_engine(configuration.bootstrap_url)
    migrator_role = _quote_identifier(configuration.migrator_role)
    app_role = _quote_identifier(configuration.app_role)
    database_name = f'"{configuration.database_name}"'
    try:
        async with bootstrap_engine.begin() as connection:
            for role, password in (
                (migrator_role, configuration.migrator_password),
                (app_role, configuration.app_password),
            ):
                await connection.execute(text(f"""
                    DO $$ BEGIN
                        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role[1:-1]}') THEN
                            CREATE ROLE {role} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB;
                        END IF;
                    END $$
                """))
                await connection.execute(
                    text(
                        f"ALTER ROLE {role} WITH LOGIN NOSUPERUSER NOBYPASSRLS "
                        f"NOCREATEROLE NOCREATEDB PASSWORD {_quote_literal(password)}"
                    ),
                )
            await connection.execute(text("DROP SCHEMA IF EXISTS ire CASCADE"))
            await connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
            await connection.execute(text(f"GRANT CONNECT, CREATE ON DATABASE {database_name} TO {migrator_role}"))
            await connection.execute(text(f"GRANT CONNECT ON DATABASE {database_name} TO {app_role}"))
            await connection.execute(text(f"GRANT USAGE, CREATE ON SCHEMA public TO {migrator_role}"))
            await connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {app_role}"))
    finally:
        await bootstrap_engine.dispose()


def _assert_single_alembic_head(environment: dict[str, str]) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    heads = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    print(result.stdout, end="")
    if len(heads) != 1:
        raise RuntimeError(f"Expected exactly one Alembic head, found {len(heads)}.")


def _run_migrations(configuration: Configuration) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = configuration.migrator_url
    _assert_single_alembic_head(environment)
    _run([sys.executable, "-m", "alembic", "upgrade", "head"], env=environment)


async def _grant_serving_access(configuration: Configuration) -> None:
    bootstrap_engine = create_async_engine(configuration.bootstrap_url)
    app_role = _quote_identifier(configuration.app_role)
    try:
        async with bootstrap_engine.begin() as connection:
            await connection.execute(text(f"GRANT USAGE ON SCHEMA ire TO {app_role}"))
            await connection.execute(text(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA ire TO {app_role}"))
            await connection.execute(
                text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {app_role}")
            )
    finally:
        await bootstrap_engine.dispose()


def _signing_key() -> str:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return base64.b64encode(pem).decode("ascii")


def _production_environment(configuration: Configuration, *, include_oidc: bool) -> dict[str, str]:
    environment = {
        "IRE_ENV": "production",
        "DATABASE_URL": configuration.app_url,
        "IRE_AUTO_CREATE_SCHEMA": "false",
        "REDIS_URL": "rediss://cache.example.test:6380/0",
        "PUBLIC_RATE_LIMIT_SALT": "production-rehearsal-rate-limit-salt",
        "S3_BUCKET_NAME": "production-rehearsal-private-bucket",
        "S3_SERVER_SIDE_ENCRYPTION": "aws:kms",
        "GOVERNANCE_PRIVATE_KEY": _signing_key(),
        "GOVERNANCE_KEY_ID": "production-rehearsal-key",
        "IRE_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "IRE_CORS_ALLOWED_ORIGINS": "https://reasoning.example.test",
        "REASONING_ENGINE_AI_PROVIDER": "mock",
    }
    if include_oidc:
        environment.update({
            "JWT_JWKS_URL": "https://identity.example.test/.well-known/jwks.json",
            "JWT_ISSUER": "https://identity.example.test/",
            "JWT_AUDIENCE": "institutional-reasoning-engine",
        })
    return environment


def _docker_environment_args(environment: dict[str, str]) -> list[str]:
    args: list[str] = []
    for key, value in environment.items():
        args.extend(["-e", f"{key}={value}"])
    return args


def _redacted_docker_environment_args(environment: dict[str, str]) -> list[str]:
    sensitive_names = {"DATABASE_URL", "GOVERNANCE_PRIVATE_KEY", "PUBLIC_RATE_LIMIT_SALT", "REDIS_URL"}
    args: list[str] = []
    for key, value in environment.items():
        displayed = "***" if key in sensitive_names else value
        args.extend(["-e", f"{key}={displayed}"])
    return args


def _port_is_listening(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((host, port)) == 0


def _http_json(path: str, *, expected_status: int, timeout_seconds: int = 3) -> str:
    request = urllib.request.Request(f"http://127.0.0.1:8000{path}", headers={"Host": "127.0.0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
            status = response.status
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8")
        status = error.code
    if status != expected_status:
        raise RuntimeError(f"{path} returned HTTP {status}, expected {expected_status}: {body}")
    print(f"{path} -> HTTP {status} {body}", flush=True)
    return body


def _wait_for_http(path: str, *, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            _http_json(path, expected_status=200)
            return
        except Exception as error:
            last_error = error
            time.sleep(1)
    raise RuntimeError(f"{path} did not become ready within {timeout_seconds}s: {last_error}")


def _assert_missing_oidc_fails_closed(docker: str, image_tag: str, configuration: Configuration) -> None:
    command = [
        docker,
        "run",
        "--rm",
        "--network",
        "host",
        *_docker_environment_args(_production_environment(configuration, include_oidc=False)),
        image_tag,
    ]
    result = subprocess.run(command, cwd=PROJECT_ROOT, text=True, capture_output=True, timeout=30)
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    if result.returncode == 0:
        raise RuntimeError("Production container started without required OIDC configuration.")
    if "JWT_JWKS_URL" not in result.stdout + result.stderr:
        raise RuntimeError("Missing-OIDC failure did not report the expected fail-closed boundary.")


def _run_application_container(docker: str, image_tag: str, configuration: Configuration, timeout_seconds: int) -> None:
    if _port_is_listening("127.0.0.1", 8000):
        raise RuntimeError("Port 8000 is already in use; refusing to target an ambiguous application.")
    container_name = f"cacisa-production-rehearsal-{os.getpid()}"
    subprocess.run([docker, "rm", "-f", container_name], cwd=PROJECT_ROOT, text=True, capture_output=True, timeout=15)
    try:
        environment = _production_environment(configuration, include_oidc=True)
        command = [
            docker,
            "run",
            "-d",
            "--name",
            container_name,
            "--network",
            "host",
            *_docker_environment_args(environment),
            image_tag,
        ]
        display_command = [
            docker,
            "run",
            "-d",
            "--name",
            container_name,
            "--network",
            "host",
            *_redacted_docker_environment_args(environment),
            image_tag,
        ]
        _run(command, display_command=display_command)
        _wait_for_http("/health/live", timeout_seconds=timeout_seconds)
        _wait_for_http("/health/ready", timeout_seconds=timeout_seconds)
        _http_json("/api/v1/public/policy-guides", expected_status=200)
        protected_statuses = {401, 403}
        try:
            _http_json("/api/v1/session/capabilities", expected_status=403)
        except RuntimeError:
            _http_json("/api/v1/session/capabilities", expected_status=401)
        print("Protected route rejected anonymous access with one of " + ", ".join(str(status) for status in sorted(protected_statuses)), flush=True)
    finally:
        _run([docker, "rm", "-f", container_name], timeout=30)


async def _reset_schemas(configuration: Configuration) -> None:
    bootstrap_engine = create_async_engine(configuration.bootstrap_url)
    try:
        async with bootstrap_engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA IF EXISTS ire CASCADE"))
            await connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
    finally:
        await bootstrap_engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the disposable production-stack rehearsal.")
    parser.add_argument("--no-postgres-compose", action="store_true", help="Use an already-running PostgreSQL service.")
    parser.add_argument("--compose-file", default="docker-compose.production-rehearsal.yml")
    parser.add_argument("--image-tag", default=f"institutional-reasoning-engine-production-rehearsal:{os.getpid()}")
    parser.add_argument("--timeout-seconds", type=int, default=90)
    args = parser.parse_args()

    configuration = _configuration()
    docker = _docker()
    compose_started = False
    try:
        if not args.no_postgres_compose:
            if _port_is_listening("127.0.0.1", int(DEFAULT_PORT)):
                raise RuntimeError(f"Port {DEFAULT_PORT} is already in use; refusing to target an ambiguous database.")
            _run([docker, "compose", "-f", args.compose_file, "up", "-d"])
            compose_started = True
        asyncio.run(_wait_for_database(configuration.bootstrap_url, args.timeout_seconds))
        asyncio.run(_bootstrap_database(configuration))
        _run_migrations(configuration)
        asyncio.run(_grant_serving_access(configuration))
        _run([docker, "build", "--pull=false", "--tag", args.image_tag, "."])
        _assert_missing_oidc_fails_closed(docker, args.image_tag, configuration)
        _run_application_container(docker, args.image_tag, configuration, args.timeout_seconds)
        return 0
    finally:
        try:
            asyncio.run(_reset_schemas(configuration))
        finally:
            if compose_started:
                _run([docker, "compose", "-f", args.compose_file, "down", "-v"], timeout=60)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from None
