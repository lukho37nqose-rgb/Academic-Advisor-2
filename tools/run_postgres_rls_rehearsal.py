"""Run the disposable PostgreSQL RLS verification workflow."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

import asyncpg


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = "5433"
DEFAULT_BOOTSTRAP_URL = f"postgresql+asyncpg://postgres:postgres@127.0.0.1:{DEFAULT_PORT}/ire_rls_rehearsal"
DEFAULT_MIGRATOR_URL = (
    f"postgresql+asyncpg://ire_migrator_rehearsal:migrator-rehearsal-password"
    f"@127.0.0.1:{DEFAULT_PORT}/ire_rls_rehearsal"
)
DEFAULT_APP_URL = (
    f"postgresql+asyncpg://ire_app_rehearsal:app-rehearsal-password"
    f"@127.0.0.1:{DEFAULT_PORT}/ire_rls_rehearsal"
)


def _run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=True)


def _rls_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.setdefault("IRE_RLS_ALLOW_DESTRUCTIVE_REHEARSAL", "confirmed")
    environment.setdefault("IRE_RLS_BOOTSTRAP_URL", DEFAULT_BOOTSTRAP_URL)
    environment.setdefault("IRE_RLS_MIGRATOR_URL", DEFAULT_MIGRATOR_URL)
    environment.setdefault("IRE_RLS_APP_URL", DEFAULT_APP_URL)
    return environment


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


def _docker_command() -> str:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("Docker is required for the local PostgreSQL rehearsal but was not found on PATH.")
    return docker


def _port_is_listening(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((host, port)) == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the disposable PostgreSQL RLS rehearsal.")
    parser.add_argument("--no-compose", action="store_true", help="Use an already-running PostgreSQL service.")
    parser.add_argument("--keep-running", action="store_true", help="Do not stop the compose service after the run.")
    parser.add_argument("--compose-file", default="docker-compose.rls.yml")
    parser.add_argument("--timeout-seconds", type=int, default=60)
    args = parser.parse_args()

    environment = _rls_environment()
    compose_started = False
    docker = None if args.no_compose else _docker_command()

    try:
        if docker:
            if _port_is_listening("127.0.0.1", int(DEFAULT_PORT)):
                raise RuntimeError(f"Port {DEFAULT_PORT} is already in use; refusing to target an ambiguous database.")
            _run([docker, "compose", "-f", args.compose_file, "up", "-d"])
            compose_started = True
        asyncio.run(_wait_for_database(environment["IRE_RLS_BOOTSTRAP_URL"], args.timeout_seconds))
        _assert_single_alembic_head(environment)
        _run([sys.executable, "-m", "pytest", "tests/integration/test_postgres_rls.py", "-q"], env=environment)
        return 0
    finally:
        if docker and compose_started and not args.keep_running:
            _run([docker, "compose", "-f", args.compose_file, "down", "-v"])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from None
