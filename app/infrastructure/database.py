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
    "metadata_overrides", "metadata_quick_edits", "releases", "rule_graphs", "workflow_outbox",
    "system_record_import_mappings", "system_record_import_mapping_events",
    "institutional_data_sources",
    "evidence", "evidence_fact_proposals", "evidence_fact_proposal_events", "claims", "facts", "support_requests", "support_request_events",
    "decision_review_cases", "decision_review_case_events", "reasoning_graphs",
    "evidence_deletion_events", "fact_supersession_events", "reasoning_graph_deletion_events",
    "shadow_calibration_suites", "shadow_calibration_cases", "shadow_calibration_suite_events",
    "shadow_calibration_runs", "shadow_calibration_findings",
    "institutional_context_events", "institutional_context_event_attestations",
    "provider_tenant_controls", "provider_support_access_requests",
)

_IMMUTABLE_DECISION_ARTIFACT_TRIGGERS = {
    "evidence": "prevent_evidence_mutation",
    "claims": "prevent_claims_mutation",
    "facts": "prevent_facts_mutation",
    "reasoning_graphs": "prevent_reasoning_graphs_mutation",
    "releases": "prevent_releases_mutation",
    "rule_graphs": "prevent_rule_graphs_mutation",
    "evidence_deletion_events": "prevent_evidence_deletion_events_mutation",
    "fact_supersession_events": "prevent_fact_supersession_events_mutation",
    "reasoning_graph_deletion_events": "prevent_reasoning_graph_deletion_events_mutation",
}


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
        trigger_rows = await connection.execute(text("""
            SELECT relation.relname, trigger.tgname
            FROM pg_trigger AS trigger
            JOIN pg_class AS relation ON relation.oid = trigger.tgrelid
            JOIN pg_namespace AS schema ON schema.oid = relation.relnamespace
            WHERE NOT trigger.tgisinternal
                AND schema.nspname = 'public'
                AND relation.relname = ANY(CAST(:table_names AS text[]))
        """), {"table_names": list(_IMMUTABLE_DECISION_ARTIFACT_TRIGGERS)})
        installed_triggers = {(row.relname, row.tgname) for row in trigger_rows}
        missing_triggers = [
            f"{table_name}.{trigger_name}"
            for table_name, trigger_name in _IMMUTABLE_DECISION_ARTIFACT_TRIGGERS.items()
            if (table_name, trigger_name) not in installed_triggers
        ]
        if missing_triggers:
            raise RuntimeError(
                "Production database is missing immutable decision-artifact triggers for: "
                + ", ".join(missing_triggers)
            )

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency provider for FastAPI."""
    async with AsyncSessionLocal() as session:
        yield session
