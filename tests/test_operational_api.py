import asyncio
import re

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import app
from app.infrastructure.database import get_db_session


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
