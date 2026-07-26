"""Executable PostgreSQL RLS rehearsal using separate migration and serving roles.

This test is intentionally skipped unless its three explicit connection URLs and
destructive-rehearsal acknowledgement are supplied. It resets only the dedicated
``ire_rls_rehearsal`` database and only accepts roles ending in ``_rehearsal``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker, create_async_engine

from app.infrastructure.database import _RLS_TABLES, validate_production_database_safety
from app.services.tenant_context import (
    begin_request_scope,
    public_support_request_scope,
    reset_request_scope,
    tenant_scope,
)


pytestmark = pytest.mark.postgres_rls

_REHEARSAL_DATABASE = "ire_rls_rehearsal"
_ROLE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,62}_rehearsal$")
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RehearsalConfiguration:
    bootstrap_url: str
    migrator_url: str
    app_url: str
    database_name: str
    migrator_role: str
    migrator_password: str
    app_role: str
    app_password: str


def _url_identity(url: str, setting_name: str) -> tuple[str, str, str]:
    parsed = urlsplit(url)
    if parsed.scheme != "postgresql+asyncpg" or not parsed.hostname:
        pytest.fail(f"{setting_name} must be a postgresql+asyncpg URL.")
    database_name = unquote(parsed.path.lstrip("/"))
    role = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    if not database_name or not role or not password:
        pytest.fail(f"{setting_name} must include a database, role, and password.")
    return database_name, role, password


def _quote_identifier(value: str) -> str:
    if not _ROLE_PATTERN.fullmatch(value):
        pytest.fail("RLS rehearsal roles must end in '_rehearsal' and use lowercase SQL identifiers.")
    return f'"{value}"'


def _quote_literal(value: str) -> str:
    """Quotes a password for PostgreSQL role DDL without relying on utility binds."""
    return "'" + value.replace("'", "''") + "'"


def _configuration() -> RehearsalConfiguration:
    settings = {
        "IRE_RLS_BOOTSTRAP_URL": os.environ.get("IRE_RLS_BOOTSTRAP_URL", ""),
        "IRE_RLS_MIGRATOR_URL": os.environ.get("IRE_RLS_MIGRATOR_URL", ""),
        "IRE_RLS_APP_URL": os.environ.get("IRE_RLS_APP_URL", ""),
    }
    if not any(settings.values()):
        pytest.skip("PostgreSQL RLS rehearsal is not configured.")
    missing = [name for name, value in settings.items() if not value]
    if missing:
        pytest.fail("RLS rehearsal is missing: " + ", ".join(missing))
    if os.environ.get("IRE_RLS_ALLOW_DESTRUCTIVE_REHEARSAL") != "confirmed":
        pytest.fail("Set IRE_RLS_ALLOW_DESTRUCTIVE_REHEARSAL=confirmed for the dedicated rehearsal database.")

    bootstrap_database, _bootstrap_role, _bootstrap_password = _url_identity(
        settings["IRE_RLS_BOOTSTRAP_URL"], "IRE_RLS_BOOTSTRAP_URL"
    )
    migrator_database, migrator_role, migrator_password = _url_identity(
        settings["IRE_RLS_MIGRATOR_URL"], "IRE_RLS_MIGRATOR_URL"
    )
    app_database, app_role, app_password = _url_identity(settings["IRE_RLS_APP_URL"], "IRE_RLS_APP_URL")
    if {bootstrap_database, migrator_database, app_database} != {_REHEARSAL_DATABASE}:
        pytest.fail(f"RLS rehearsal may only target the dedicated {_REHEARSAL_DATABASE} database.")
    _quote_identifier(migrator_role)
    _quote_identifier(app_role)
    if migrator_role == app_role:
        pytest.fail("RLS rehearsal requires distinct migration and serving roles.")
    return RehearsalConfiguration(
        bootstrap_url=settings["IRE_RLS_BOOTSTRAP_URL"],
        migrator_url=settings["IRE_RLS_MIGRATOR_URL"],
        app_url=settings["IRE_RLS_APP_URL"],
        database_name=bootstrap_database,
        migrator_role=migrator_role,
        migrator_password=migrator_password,
        app_role=app_role,
        app_password=app_password,
    )


async def _set_scope(
    connection: AsyncConnection,
    *,
    tenant_id: str = "",
    access_mode: str = "tenant",
    support_request_id: str = "",
) -> None:
    await connection.execute(
        text("SELECT set_config('ire.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )
    await connection.execute(
        text("SELECT set_config('ire.access_mode', :access_mode, true)"),
        {"access_mode": access_mode},
    )
    await connection.execute(
        text("SELECT set_config('ire.public_support_request_id', :request_id, true)"),
        {"request_id": support_request_id},
    )


async def _bootstrap_database(configuration: RehearsalConfiguration) -> None:
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


def _run_migrations(configuration: RehearsalConfiguration) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = configuration.migrator_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail("Migration-role RLS rehearsal failed:\n" + result.stdout + result.stderr)


async def _grant_serving_access(configuration: RehearsalConfiguration) -> None:
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


async def _reset_schemas(configuration: RehearsalConfiguration) -> None:
    bootstrap_engine = create_async_engine(configuration.bootstrap_url)
    try:
        async with bootstrap_engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA IF EXISTS ire CASCADE"))
            await connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
    finally:
        await bootstrap_engine.dispose()


async def _assert_production_startup_database_check(app_url: str) -> None:
    """Runs the same PostgreSQL guard that the production API lifespan invokes."""
    app_engine = create_async_engine(app_url)
    original_environment = os.environ.get("IRE_ENV")
    os.environ["IRE_ENV"] = "production"
    try:
        await validate_production_database_safety(database_engine=app_engine)
    finally:
        if original_environment is None:
            os.environ.pop("IRE_ENV", None)
        else:
            os.environ["IRE_ENV"] = original_environment
        await app_engine.dispose()


@pytest.fixture(scope="module")
def postgres_rls_environment() -> Iterator[RehearsalConfiguration]:
    configuration = _configuration()
    asyncio.run(_bootstrap_database(configuration))
    _run_migrations(configuration)
    asyncio.run(_grant_serving_access(configuration))
    try:
        yield configuration
    finally:
        asyncio.run(_reset_schemas(configuration))


async def _seed_two_tenants(app_url: str) -> None:
    app_engine = create_async_engine(app_url)
    try:
        fixtures = (
            ("tenant_uct", "dom_public", "rel_public", "graph_public", "draft_uct", "evidence_uct", True),
            ("tenant_other", "dom_private", "rel_private", "graph_private", "draft_other", "evidence_other", False),
        )
        for tenant_id, domain_id, release_id, graph_id, draft_id, evidence_id, is_public in fixtures:
            schema_definition = json.dumps({
                "access": {
                    "public_policy_guide": is_public,
                    "assistance_requests_enabled": is_public,
                }
            })
            async with app_engine.begin() as connection:
                await _set_scope(connection, tenant_id=tenant_id)
                await connection.execute(
                    text("INSERT INTO tenants (id, name) VALUES (:id, :name)"),
                    {"id": tenant_id, "name": tenant_id},
                )
                await connection.execute(
                    text("""
                        INSERT INTO domains (id, tenant_id, name, schema_definition)
                        VALUES (:id, :tenant_id, :name, CAST(:schema_definition AS jsonb))
                    """),
                    {
                        "id": domain_id,
                        "tenant_id": tenant_id,
                        "name": domain_id,
                        "schema_definition": schema_definition,
                    },
                )
                await connection.execute(
                    text("""
                        INSERT INTO policy_drafts (id, tenant_id, domain_id, policy_name, author_id, payload)
                        VALUES (:id, :tenant_id, :domain_id, 'Eligibility policy', 'author_1', CAST('{}' AS jsonb))
                    """),
                    {"id": draft_id, "tenant_id": tenant_id, "domain_id": domain_id},
                )
                mapping_contract = json.dumps({
                    "format_version": "1.0",
                    "mapping_id": "rehearsal",
                    "source_system": "Synthetic registrar",
                    "subject_identifier_column": "record_id",
                    "source_record_version_column": "version",
                    "fields": [{
                        "source_column": "credits",
                        "target_path": "facts.completed_credits",
                        "value_type": "integer",
                        "required": True,
                    }],
                    "max_rows": 10_000,
                    "max_bytes": 20_000_000,
                })
                await connection.execute(
                    text("""
                        INSERT INTO system_record_import_mappings
                        (id, tenant_id, domain_id, mapping_name, source_system, contract, contract_sha256, author_id, status)
                        VALUES
                        (:id, :tenant_id, :domain_id, 'Rehearsal export', 'Synthetic registrar',
                         CAST(:contract AS jsonb),
                         :hash, 'author_1', 'PENDING')
                    """),
                    {
                        "id": f"mapping_{tenant_id}",
                        "tenant_id": tenant_id,
                        "domain_id": domain_id,
                        "contract": mapping_contract,
                        "hash": "a" * 64,
                    },
                )
                await connection.execute(
                    text("""
                        INSERT INTO system_record_import_mapping_events
                        (id, mapping_id, tenant_id, domain_id, sequence, event_type, actor_id)
                        VALUES (:id, :mapping_id, :tenant_id, :domain_id, 1, 'SUBMITTED', 'author_1')
                    """),
                    {
                        "id": f"mapping_event_{tenant_id}",
                        "mapping_id": f"mapping_{tenant_id}",
                        "tenant_id": tenant_id,
                        "domain_id": domain_id,
                    },
                )
                await connection.execute(
                    text("""
                        INSERT INTO background_jobs
                        (id, tenant_id, domain_id, job_type, resource_id, deduplication_key)
                        VALUES
                        (:id, :tenant_id, :domain_id, 'HANDBOOK_TEXT_EXTRACTION', :resource_id, :deduplication_key)
                    """),
                    {
                        "id": f"job_{tenant_id}",
                        "tenant_id": tenant_id,
                        "domain_id": domain_id,
                        "resource_id": f"handbook_{tenant_id}",
                        "deduplication_key": f"HANDBOOK_TEXT_EXTRACTION:handbook_{tenant_id}",
                    },
                )
                await connection.execute(
                    text("""
                        INSERT INTO releases (id, domain_id, version, rule_graph_id, digital_signature)
                        VALUES (:id, :domain_id, '2026.1', :graph_id, 'rehearsal-signature')
                    """),
                    {"id": release_id, "domain_id": domain_id, "graph_id": graph_id},
                )
                await connection.execute(
                    text("""
                        INSERT INTO rule_graphs (id, release_id, compiled_bytecode)
                        VALUES (:id, :release_id, CAST('{}' AS jsonb))
                    """),
                    {"id": graph_id, "release_id": release_id},
                )
                await connection.execute(
                    text("""
                        INSERT INTO evidence (id, tenant_id, domain_id, subject_id, source_type, cryptographic_hash)
                        VALUES (:id, :tenant_id, :domain_id, 'subject_1', 'rehearsal', :hash)
                    """),
                    {"id": evidence_id, "tenant_id": tenant_id, "domain_id": domain_id, "hash": evidence_id},
                )
    finally:
        await app_engine.dispose()


@pytest.fixture(scope="module")
def seeded_postgres_rls_environment(postgres_rls_environment: RehearsalConfiguration) -> RehearsalConfiguration:
    asyncio.run(_seed_two_tenants(postgres_rls_environment.app_url))
    return postgres_rls_environment


def test_serving_role_and_every_protected_table_have_enforced_rls(
    postgres_rls_environment: RehearsalConfiguration,
) -> None:
    async def verify() -> None:
        bootstrap_engine = create_async_engine(postgres_rls_environment.bootstrap_url)
        try:
            async with bootstrap_engine.connect() as connection:
                role = (await connection.execute(text("""
                    SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb
                    FROM pg_roles
                    WHERE rolname = :role_name
                """), {"role_name": postgres_rls_environment.app_role})).mappings().one()
                assert not any(bool(role[field]) for field in role)

                result = await connection.execute(text("""
                    SELECT relation.relname, relation.relrowsecurity, relation.relforcerowsecurity
                    FROM pg_class AS relation
                    JOIN pg_namespace AS schema ON schema.oid = relation.relnamespace
                    WHERE relation.relkind = 'r'
                    AND schema.nspname = 'public'
                    AND relation.relname = ANY(CAST(:table_names AS text[]))
                """), {"table_names": list(_RLS_TABLES)})
                protected_tables = {row.relname: row for row in result}
                assert set(protected_tables) == set(_RLS_TABLES)
                assert all(row.relrowsecurity and row.relforcerowsecurity for row in protected_tables.values())
        finally:
            await bootstrap_engine.dispose()

    asyncio.run(verify())
    asyncio.run(_assert_production_startup_database_check(postgres_rls_environment.app_url))


def test_serving_session_cannot_read_update_or_insert_across_tenants(
    seeded_postgres_rls_environment: RehearsalConfiguration,
) -> None:
    async def verify() -> None:
        app_engine = create_async_engine(seeded_postgres_rls_environment.app_url)
        session_factory = async_sessionmaker(bind=app_engine, expire_on_commit=False)
        try:
            with tenant_scope("tenant_uct"):
                async with session_factory() as session:
                    visible_drafts = (await session.execute(
                        text("SELECT id FROM policy_drafts ORDER BY id")
                    )).scalars().all()
                    assert visible_drafts == ["draft_uct"]
                    hidden_release = (await session.execute(
                        text("SELECT id FROM releases WHERE id = 'rel_private'")
                    )).scalars().all()
                    assert hidden_release == []
                    visible_mappings = (await session.execute(
                        text("SELECT id FROM system_record_import_mappings ORDER BY id")
                    )).scalars().all()
                    visible_mapping_events = (await session.execute(
                        text("SELECT id FROM system_record_import_mapping_events ORDER BY id")
                    )).scalars().all()
                    visible_jobs = (await session.execute(
                        text("SELECT id FROM background_jobs ORDER BY id")
                    )).scalars().all()
                    assert visible_mappings == ["mapping_tenant_uct"]
                    assert visible_mapping_events == ["mapping_event_tenant_uct"]
                    assert visible_jobs == ["job_tenant_uct"]
                    await session.execute(text("""
                        UPDATE policy_drafts
                        SET policy_name = 'cross-tenant mutation'
                        WHERE id = 'draft_other'
                    """))
                    await session.commit()

            with tenant_scope("tenant_uct"):
                async with session_factory() as session:
                    with pytest.raises(DBAPIError):
                        await session.execute(text("""
                            UPDATE system_record_import_mappings
                            SET mapping_name = 'rewritten'
                            WHERE id = 'mapping_tenant_uct'
                        """))

                async with session_factory() as session:
                    with pytest.raises(DBAPIError):
                        await session.execute(text("""
                            UPDATE system_record_import_mapping_events
                            SET actor_id = 'rewritten'
                            WHERE id = 'mapping_event_tenant_uct'
                        """))

            with tenant_scope("tenant_other"):
                async with session_factory() as session:
                    policy_name = await session.scalar(text("""
                        SELECT policy_name FROM policy_drafts WHERE id = 'draft_other'
                    """))
                    assert policy_name == "Eligibility policy"

            with tenant_scope("tenant_uct"):
                async with session_factory() as session:
                    with pytest.raises(DBAPIError):
                        await session.execute(text("""
                            INSERT INTO background_jobs
                            (id, tenant_id, domain_id, job_type, resource_id, deduplication_key)
                            VALUES
                            ('job_illegal', 'tenant_other', 'dom_private', 'HANDBOOK_TEXT_EXTRACTION',
                             'handbook_illegal', 'HANDBOOK_TEXT_EXTRACTION:handbook_illegal')
                        """))
                async with session_factory() as session:
                    with pytest.raises(DBAPIError):
                        await session.execute(text("""
                            INSERT INTO policy_drafts (id, tenant_id, domain_id, policy_name, author_id, payload)
                            VALUES ('draft_illegal', 'tenant_other', 'dom_private', 'Illegal', 'author_1', CAST('{}' AS jsonb))
                        """))
        finally:
            await app_engine.dispose()

    asyncio.run(verify())


def test_public_scope_exposes_only_an_explicit_policy_guide_and_one_initial_support_event(
    seeded_postgres_rls_environment: RehearsalConfiguration,
) -> None:
    async def verify() -> None:
        app_engine = create_async_engine(seeded_postgres_rls_environment.app_url)
        session_factory = async_sessionmaker(bind=app_engine, expire_on_commit=False)
        try:
            request_tokens = begin_request_scope(public=True)
            try:
                async with session_factory() as session:
                    visible_domains = (await session.execute(text("SELECT id FROM domains ORDER BY id"))).scalars().all()
                    visible_releases = (await session.execute(text("SELECT id FROM releases ORDER BY id"))).scalars().all()
                    visible_graphs = (await session.execute(text("SELECT id FROM rule_graphs ORDER BY id"))).scalars().all()
                    hidden_evidence = (await session.execute(text("SELECT id FROM evidence ORDER BY id"))).scalars().all()
                    assert visible_domains == ["dom_public"]
                    assert visible_releases == ["rel_public"]
                    assert visible_graphs == ["graph_public"]
                    assert hidden_evidence == []

                with public_support_request_scope("support_expected"):
                    async with session_factory() as session:
                        with pytest.raises(DBAPIError):
                            await session.execute(text("""
                                INSERT INTO support_requests (id, tenant_id, domain_id, category, message, status)
                                VALUES ('support_wrong', 'tenant_uct', 'dom_public', 'general', 'Need help', 'OPEN')
                            """))

                    async with session_factory() as session:
                        await session.execute(text("""
                            INSERT INTO support_requests (id, tenant_id, domain_id, category, message, status)
                            VALUES ('support_expected', 'tenant_uct', 'dom_public', 'general', 'Need help', 'OPEN')
                        """))
                        await session.execute(text("""
                            INSERT INTO support_request_events
                            (id, support_request_id, tenant_id, domain_id, sequence, status, actor_id)
                            VALUES
                            ('support_event_expected', 'support_expected', 'tenant_uct', 'dom_public', 1, 'OPEN', 'public_submission')
                        """))
                        await session.commit()

                async with session_factory() as session:
                    hidden_support = (await session.execute(text("SELECT id FROM support_requests"))).scalars().all()
                    assert hidden_support == []
            finally:
                reset_request_scope(request_tokens)

            with tenant_scope("tenant_uct"):
                async with session_factory() as session:
                    support = (await session.execute(text("SELECT id FROM support_requests"))).scalars().all()
                    assert support == ["support_expected"]
        finally:
            await app_engine.dispose()

    asyncio.run(verify())
