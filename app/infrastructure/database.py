"""
Database Configuration and Session Management.
"""
import os
import logging
from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import Session
from app.infrastructure.db import Base
from app.services.tenant_context import (
    current_access_mode,
    current_public_support_request_id,
    current_tenant_id,
)

logger = logging.getLogger(__name__)

# Postgres integration: Uses asyncpg if provided, otherwise gracefully falls back to local SQLite.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./reasoning_engine.db")

# Detect connection string type for diagnostics
is_postgres = "postgresql" in DATABASE_URL
if is_postgres:
    logger.info("Initializing connection to PostgreSQL database cluster...")
else:
    logger.info("Initializing connection to local SQLite sandbox database...")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

_RLS_TABLES = (
    "tenants", "domains", "policy_drafts", "policy_ambiguities",
    "policy_ambiguity_events", "handbook_uploads", "handbook_upload_sessions",
    "handbook_pages", "handbook_ocr_reviews", "handbook_ocr_review_events",
    "background_jobs",
    "metadata_overrides", "metadata_quick_edits", "releases", "rule_graphs",
    "system_record_import_mappings", "system_record_import_mapping_events",
    "evidence", "claims", "facts", "support_requests", "support_request_events",
    "decision_review_cases", "decision_review_case_events", "reasoning_graphs",
)


@event.listens_for(Session, "after_begin")
def apply_rls_context(session: Session, transaction, connection) -> None:
    """Sets transaction-local RLS context again after every repository commit."""
    del session, transaction
    if connection.dialect.name != "postgresql":
        return
    connection.execute(
        text("SELECT set_config('ire.tenant_id', :tenant_id, true)"),
        {"tenant_id": current_tenant_id() or ""},
    )
    connection.execute(
        text("SELECT set_config('ire.access_mode', :access_mode, true)"),
        {"access_mode": current_access_mode()},
    )
    connection.execute(
        text("SELECT set_config('ire.public_support_request_id', :request_id, true)"),
        {"request_id": current_public_support_request_id() or ""},
    )

async def init_db():
    """Optional development-only schema creation; production uses Alembic."""
    if os.environ.get("IRE_AUTO_CREATE_SCHEMA", "false").lower() != "true":
        logger.info("Schema initialization skipped; run `python -m alembic upgrade head` before startup.")
        return
    logger.warning("IRE_AUTO_CREATE_SCHEMA is enabled; this is not a production migration path.")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def validate_production_database_safety(*, database_engine: AsyncEngine | None = None) -> None:
    """Confirms that the serving database role cannot silently bypass RLS."""
    if os.environ.get("IRE_ENV", "development").lower() != "production":
        return
    active_engine = database_engine or engine
    async with active_engine.connect() as connection:
        role = (await connection.execute(text(
            """
            SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb
            FROM pg_roles
            WHERE rolname = current_user
            """
        ))).first()
        if (
            role is None
            or bool(role.rolsuper)
            or bool(role.rolbypassrls)
            or bool(role.rolcreaterole)
            or bool(role.rolcreatedb)
        ):
            raise RuntimeError(
                "Production serving database role must not be superuser, BYPASSRLS, CREATEROLE, or CREATEDB."
            )
        result = await connection.execute(text("""
            SELECT relation.relname, relation.relrowsecurity, relation.relforcerowsecurity
            FROM pg_class AS relation
            JOIN pg_namespace AS schema ON schema.oid = relation.relnamespace
            WHERE relation.relkind = 'r'
            AND schema.nspname = 'public'
            AND relation.relname = ANY(CAST(:table_names AS text[]))
        """), {"table_names": list(_RLS_TABLES)})
        rows = {row.relname: row for row in result}
        unsafe = [
            table_name for table_name in _RLS_TABLES
            if table_name not in rows
            or not bool(rows[table_name].relrowsecurity)
            or not bool(rows[table_name].relforcerowsecurity)
        ]
        if unsafe:
            raise RuntimeError(
                "Production database is missing forced row-level security for: " + ", ".join(unsafe)
            )

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency provider for FastAPI."""
    async with AsyncSessionLocal() as session:
        yield session
