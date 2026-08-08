import asyncio
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import app
from app.infrastructure.database import expected_schema_heads, get_db_session, validate_database_readiness


def test_health_probes_and_request_correlation_id(tmp_path):
    database_path = tmp_path / "health.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _test_db_session
    try:
        with TestClient(app) as client:
            live = client.get("/health/live", headers={"X-Request-ID": "pilot-check_001"})
            ready = client.get("/health/ready", headers={"X-Request-ID": "not valid/request id"})
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        asyncio.run(engine.dispose())

    assert live.status_code == 200
    assert live.json() == {"status": "ok", "service": "institutional-reasoning-engine"}
    assert live.headers["X-Request-ID"] == "pilot-check_001"
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "service": "institutional-reasoning-engine"}
    assert re.fullmatch(r"[0-9a-f]{32}", ready.headers["X-Request-ID"])


def test_production_database_readiness_requires_applied_alembic_head(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("IRE_ENV", "production")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'readiness.db'}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def exercise() -> None:
        async with session_factory() as session:
            with pytest.raises(RuntimeError, match="Alembic head"):
                await validate_database_readiness(session)
        async with engine.begin() as connection:
            await connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            await connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:version_num)"),
                {"version_num": next(iter(expected_schema_heads()))},
            )
        async with session_factory() as session:
            await validate_database_readiness(session)

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(engine.dispose())
