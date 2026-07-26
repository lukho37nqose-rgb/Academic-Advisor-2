from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import app
from app.infrastructure.database import get_db_session
from app.infrastructure.db import Base, DBDomain, DBTenant
from app.services.auth import Role, UserIdentity, get_current_user


async def _create_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def _store_domain(session_factory) -> None:
    async with session_factory() as session:
        session.add(DBTenant(id="tenant_mapping", name="Mapping Institution"))
        session.add(
            DBDomain(
                id="dom_mapping",
                tenant_id="tenant_mapping",
                name="Mapping Domain",
                schema_definition={
                    "type": "object",
                    "properties": {
                        "facts": {
                            "type": "object",
                            "properties": {
                                "completed_credits": {"type": "number", "title": "Completed credits"},
                            },
                        }
                    },
                },
            )
        )
        await session.commit()


def _author() -> UserIdentity:
    return UserIdentity(
        tenant_id="tenant_mapping",
        role=Role.RULE_AUTHOR,
        user_id="mapping_author",
        domain_ids=["dom_mapping"],
    )


def _approver() -> UserIdentity:
    return UserIdentity(
        tenant_id="tenant_mapping",
        role=Role.RULE_APPROVER,
        user_id="mapping_approver",
        domain_ids=["dom_mapping"],
    )


def _contract() -> dict[str, object]:
    return {
        "mapping_id": "credits-export-2026",
        "source_system": "Synthetic registrar export",
        "subject_identifier_column": "record_id",
        "source_record_version_column": "version",
        "fields": [
            {
                "source_column": "credits",
                "target_path": "facts.completed_credits",
                "value_type": "integer",
                "required": True,
            }
        ],
    }


def test_system_record_mapping_requires_an_independent_review_and_keeps_history(tmp_path) -> None:
    database_path = tmp_path / "system_record_mapping.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))
    asyncio.run(_store_domain(session_factory))

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _test_db_session
    app.dependency_overrides[get_current_user] = _author
    try:
        client = TestClient(app)
        submitted = client.post(
            "/api/v1/admin/system-record-import-mappings",
            json={"domain_id": "dom_mapping", "contract": _contract()},
        )
        mapping_id = submitted.json()["mapping_id"]
        listed = client.get(
            "/api/v1/admin/system-record-import-mappings",
            params={"domain_id": "dom_mapping"},
        )
        self_approval = client.post(
            f"/api/v1/admin/system-record-import-mappings/{mapping_id}/approve",
            json={"domain_id": "dom_mapping"},
        )

        app.dependency_overrides[get_current_user] = _approver
        approved = client.post(
            f"/api/v1/admin/system-record-import-mappings/{mapping_id}/approve",
            json={"domain_id": "dom_mapping", "note": "Confirmed against the approved fact schema."},
        )
        history = client.get(
            f"/api/v1/admin/system-record-import-mappings/{mapping_id}/history",
            params={"domain_id": "dom_mapping"},
        )
        repeated_review = client.post(
            f"/api/v1/admin/system-record-import-mappings/{mapping_id}/reject",
            json={"domain_id": "dom_mapping", "reason": "Too late."},
        )
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert submitted.status_code == 201
    submitted_body = submitted.json()
    assert submitted_body["status"] == "PENDING"
    assert submitted_body["contract_sha256"] != ""
    assert "records" not in submitted_body
    assert listed.status_code == 200
    assert listed.json()["items"][0]["mapping_name"] == "credits-export-2026"
    assert self_approval.status_code == 403
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["reviewed_by"] == "mapping_approver"
    assert history.status_code == 200
    assert [event["event_type"] for event in history.json()["items"]] == ["SUBMITTED", "APPROVED"]
    assert all("records" not in event for event in history.json()["items"])
    assert repeated_review.status_code == 409


def test_system_record_mapping_rejection_requires_a_reason(tmp_path) -> None:
    database_path = tmp_path / "system_record_mapping_reject.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))
    asyncio.run(_store_domain(session_factory))

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _test_db_session
    app.dependency_overrides[get_current_user] = _author
    try:
        client = TestClient(app)
        mapping_id = client.post(
            "/api/v1/admin/system-record-import-mappings",
            json={"domain_id": "dom_mapping", "contract": _contract()},
        ).json()["mapping_id"]
        app.dependency_overrides[get_current_user] = _approver
        missing_reason = client.post(
            f"/api/v1/admin/system-record-import-mappings/{mapping_id}/reject",
            json={"domain_id": "dom_mapping", "reason": "  "},
        )
        rejected = client.post(
            f"/api/v1/admin/system-record-import-mappings/{mapping_id}/reject",
            json={"domain_id": "dom_mapping", "reason": "The source version column is not documented."},
        )
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert missing_reason.status_code == 422
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    assert rejected.json()["review_note"] == "The source version column is not documented."
