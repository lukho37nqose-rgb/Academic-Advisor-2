from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from fastapi.testclient import TestClient

from app.api import app
from app.infrastructure.database import get_db_session
from app.infrastructure.db import Base, DBBackgroundJob, DBDomain, DBTenant
from app.infrastructure import repositories
from app.infrastructure.repositories import BackgroundJobRepository
from app.services import background_worker
from app.services import background_job_signals
from app.services.auth import Role, UserIdentity, get_current_user


async def _create_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def _seed_tenant(session_factory, tenant_id: str = "tenant_jobs", domain_id: str = "dom_jobs") -> None:
    async with session_factory() as session:
        session.add(DBTenant(id=tenant_id, name="Jobs Tenant"))
        session.add(DBDomain(id=domain_id, tenant_id=tenant_id, name="Jobs Domain", schema_definition={}))
        await session.commit()


def test_background_job_deduplicates_identifier_only_work(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'background_jobs.db'}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))
    asyncio.run(_seed_tenant(session_factory))

    async def exercise() -> tuple[dict[str, object], dict[str, object], DBBackgroundJob]:
        async with session_factory() as session:
            repository = BackgroundJobRepository(session)
            first = await repository.enqueue(
                tenant_id="tenant_jobs",
                domain_id="dom_jobs",
                job_type="HANDBOOK_TEXT_EXTRACTION",
                resource_id="handbook_123",
            )
            duplicate = await repository.enqueue(
                tenant_id="tenant_jobs",
                domain_id="dom_jobs",
                job_type="HANDBOOK_TEXT_EXTRACTION",
                resource_id="handbook_123",
            )
            job = await session.get(DBBackgroundJob, str(first["job_id"]))
            assert job is not None
            return first, duplicate, job

    try:
        first, duplicate, job = asyncio.run(exercise())
    finally:
        asyncio.run(engine.dispose())

    assert first["job_id"] == duplicate["job_id"]
    assert job.resource_id == "handbook_123"
    assert not hasattr(job, "payload")
    assert "student" not in job.deduplication_key.lower()


def test_background_job_signal_payload_is_identifier_only() -> None:
    body = background_job_signals._signal_body(
        {
            "job_id": "job_123",
            "tenant_id": "tenant_jobs",
            "domain_id": "dom_jobs",
            "job_type": "HANDBOOK_TEXT_EXTRACTION",
            "resource_id": "handbook_123",
            "source_text": "must not leave the database boundary",
        }
    )
    payload = json.loads(body)

    assert payload == {
        "domain_id": "dom_jobs",
        "job_id": "job_123",
        "job_type": "HANDBOOK_TEXT_EXTRACTION",
        "resource_id": "handbook_123",
        "tenant_id": "tenant_jobs",
    }
    assert "source_text" not in payload
    assert "subject_id" not in payload


def test_background_job_enqueue_publishes_optional_wakeup_signal(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'background_signal.db'}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))
    asyncio.run(_seed_tenant(session_factory))
    signalled: list[dict[str, object]] = []

    async def publish(summary: dict[str, object]) -> bool:
        signalled.append(summary)
        return True

    monkeypatch.setattr(repositories, "publish_background_job_signal", publish)

    async def exercise() -> dict[str, object]:
        async with session_factory() as session:
            return await BackgroundJobRepository(session).enqueue(
                tenant_id="tenant_jobs",
                domain_id="dom_jobs",
                job_type="HANDBOOK_TEXT_EXTRACTION",
                resource_id="handbook_signalled",
            )

    try:
        queued = asyncio.run(exercise())
    finally:
        asyncio.run(engine.dispose())

    assert signalled == [queued]
    assert signalled[0]["tenant_id"] == "tenant_jobs"
    assert signalled[0]["resource_id"] == "handbook_signalled"
    assert "source_text" not in signalled[0]
    assert "subject_id" not in signalled[0]


def test_background_job_retries_then_retains_dead_letter(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'background_retry.db'}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))
    asyncio.run(_seed_tenant(session_factory))

    async def exercise() -> tuple[int, int, DBBackgroundJob]:
        async with session_factory() as session:
            repository = BackgroundJobRepository(session)
            queued = await repository.enqueue(
                tenant_id="tenant_jobs",
                domain_id="dom_jobs",
                job_type="HANDBOOK_TEXT_EXTRACTION",
                resource_id="handbook_retry",
                max_attempts=2,
            )
            first = await repository.claim_next(tenant_id="tenant_jobs", worker_id="worker_a", lease_seconds=30)
            assert first is not None
            first_attempts = int(first.attempts)
            assert await repository.mark_failed(
                job_id=str(first.id),
                tenant_id="tenant_jobs",
                worker_id="worker_a",
                error_message="safe failure",
                retry_delay_seconds=0,
            ) == "QUEUED"
            retried = await repository.claim_next(tenant_id="tenant_jobs", worker_id="worker_b", lease_seconds=30)
            assert retried is not None
            retried_attempts = int(retried.attempts)
            assert await repository.mark_failed(
                job_id=str(retried.id),
                tenant_id="tenant_jobs",
                worker_id="worker_b",
                error_message="safe second failure",
                retry_delay_seconds=0,
            ) == "DEAD_LETTER"
            final = await session.get(DBBackgroundJob, str(queued["job_id"]))
            assert final is not None
            return first_attempts, retried_attempts, final

    try:
        first_attempts, retried_attempts, final = asyncio.run(exercise())
    finally:
        asyncio.run(engine.dispose())

    assert first_attempts == 1
    assert retried_attempts == 2
    assert final.status == "DEAD_LETTER"
    assert final.locked_by is None
    assert final.completed_at is not None


def test_expired_worker_lease_is_reclaimed_by_the_same_tenant(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'background_lease.db'}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))
    asyncio.run(_seed_tenant(session_factory))

    async def exercise() -> DBBackgroundJob:
        async with session_factory() as session:
            repository = BackgroundJobRepository(session)
            await repository.enqueue(
                tenant_id="tenant_jobs",
                domain_id="dom_jobs",
                job_type="HANDBOOK_TEXT_EXTRACTION",
                resource_id="handbook_lease",
            )
            claimed = await repository.claim_next(tenant_id="tenant_jobs", worker_id="worker_a", lease_seconds=30)
            assert claimed is not None
            setattr(claimed, "lease_expires_at", datetime.now(timezone.utc) - timedelta(seconds=1))
            await session.commit()
            reclaimed = await repository.claim_next(tenant_id="tenant_jobs", worker_id="worker_b", lease_seconds=30)
            assert reclaimed is not None
            return reclaimed

    try:
        reclaimed = asyncio.run(exercise())
    finally:
        asyncio.run(engine.dispose())

    assert reclaimed.attempts == 2
    assert reclaimed.locked_by == "worker_b"
    assert reclaimed.status == "RUNNING"


def test_worker_processes_claimed_job_under_explicit_tenant_scope(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'background_worker.db'}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))
    asyncio.run(_seed_tenant(session_factory))
    seen: list[tuple[str, str]] = []

    async def execute(job: DBBackgroundJob) -> None:
        seen.append((str(job.tenant_id), str(job.resource_id)))

    monkeypatch.setattr(background_worker, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(background_worker, "_execute", execute)

    async def exercise() -> None:
        async with session_factory() as session:
            repository = BackgroundJobRepository(session)
            await repository.enqueue(
                tenant_id="tenant_jobs",
                domain_id="dom_jobs",
                job_type="HANDBOOK_TEXT_EXTRACTION",
                resource_id="handbook_worker",
            )
        result = await background_worker.process_next_background_job(
            "tenant_jobs",
            worker_id="worker_test",
            lease_seconds=30,
        )
        assert result is not None
        assert result.status == "SUCCEEDED"

    async def load() -> DBBackgroundJob:
        async with session_factory() as session:
            job = (await session.execute(select(DBBackgroundJob))).scalars().one()
            return job

    try:
        asyncio.run(exercise())
        job = asyncio.run(load())
    finally:
        asyncio.run(engine.dispose())

    assert seen == [("tenant_jobs", "handbook_worker")]
    assert job.status == "SUCCEEDED"
    assert job.locked_by is None


def test_production_worker_rejects_missing_tenant_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IRE_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://ire:password@database.example.test:5432/ire")
    monkeypatch.delenv("IRE_WORKER_TENANT_IDS", raising=False)

    with pytest.raises(RuntimeError, match="IRE_WORKER_TENANT_IDS"):
        background_worker.configured_worker_tenant_ids()


def test_tenant_admin_can_view_identifier_only_durable_job_state(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'background_jobs_api.db'}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))
    asyncio.run(_seed_tenant(session_factory))

    async def queue() -> None:
        async with session_factory() as session:
            await BackgroundJobRepository(session).enqueue(
                tenant_id="tenant_jobs",
                domain_id="dom_jobs",
                job_type="HANDBOOK_TEXT_EXTRACTION",
                resource_id="handbook_visible_to_admin",
            )

    async def test_session():
        async with session_factory() as session:
            yield session

    asyncio.run(queue())
    app.dependency_overrides[get_current_user] = lambda: UserIdentity(
        tenant_id="tenant_jobs",
        role=Role.TENANT_ADMIN,
        user_id="admin_1",
        domain_ids=["dom_jobs"],
    )
    app.dependency_overrides[get_db_session] = test_session
    try:
        response = TestClient(app).get("/api/v1/admin/background-jobs")
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["tenant_id"] == "tenant_jobs"
    assert items[0]["domain_id"] == "dom_jobs"
    assert items[0]["job_type"] == "HANDBOOK_TEXT_EXTRACTION"
    assert items[0]["resource_id"] == "handbook_visible_to_admin"
    assert items[0]["status"] == "QUEUED"
    assert items[0]["attempts"] == 0
    assert "storage_key" not in items[0]
    assert "source_text" not in items[0]
