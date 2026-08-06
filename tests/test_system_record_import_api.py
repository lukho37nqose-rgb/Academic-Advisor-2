from __future__ import annotations

import asyncio
import json
from typing import Any

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
        session.add(DBTenant(id="tenant_import", name="Import Institution"))
        session.add(
            DBDomain(
                id="dom_import",
                tenant_id="tenant_import",
                name="Record Import Domain",
                schema_definition={
                    "type": "object",
                    "properties": {
                        "facts": {
                            "type": "object",
                            "properties": {
                                "completed_credits": {"type": "number", "title": "Completed credits"},
                                "active_registration": {"type": "boolean", "title": "Active registration"},
                            },
                        }
                    },
                },
            )
        )
        await session.commit()


def _author() -> UserIdentity:
    return UserIdentity(
        tenant_id="tenant_import",
        role=Role.POLICY_EDITOR,
        user_id="author_1",
        domain_ids=["dom_import"],
    )


def test_guided_system_record_preview_uses_only_declared_domain_facts(tmp_path) -> None:
    database_path = tmp_path / "system_record_import.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    asyncio.run(_create_schema(engine))
    asyncio.run(_store_domain(session_factory))

    async def _test_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _test_db_session
    app.dependency_overrides[get_current_user] = _author
    contract: dict[str, Any] = {
        "mapping_id": "domain-records-v1",
        "source_system": "Synthetic records",
        "subject_identifier_column": "record_id",
        "source_record_version_column": "version",
        "fields": [
            {
                "source_column": "credits",
                "target_path": "facts.completed_credits",
                "value_type": "integer",
            },
            {
                "source_column": "active",
                "target_path": "facts.active_registration",
                "value_type": "boolean",
            },
        ],
    }
    try:
        client = TestClient(app)
        fields = client.get("/api/v1/admin/domains/dom_import/record-import-fields")
        response = client.post(
            "/api/v1/admin/system-record-imports/preview",
            data={"domain_id": "dom_import", "contract_json": json.dumps(contract)},
            files={
                "file": (
                    "records.csv",
                    b"record_id,version,credits,active\nsubject_1,2,120,true\n",
                    "text/csv",
                )
            },
        )
        contract["fields"][0]["target_path"] = "facts.undeclared"
        rejected = client.post(
            "/api/v1/admin/system-record-imports/preview",
            data={"domain_id": "dom_import", "contract_json": json.dumps(contract)},
            files={"file": ("records.csv", b"record_id,version,credits,active\nsubject_1,2,120,true\n", "text/csv")},
        )
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert fields.status_code == 200
    assert fields.json()["items"] == [
        {"target_path": "facts.active_registration", "label": "Active registration", "schema_type": "boolean"},
        {"target_path": "facts.completed_credits", "label": "Completed credits", "schema_type": "number"},
    ]
    assert response.status_code == 200
    assert response.json()["accepted_record_count"] == 1
    assert "records" not in response.json()
    assert rejected.status_code == 422
