"""Enforce PostgreSQL RLS rehearsal findings.

Revision ID: 8d3f2a9c1b70
Revises: f8c2d9a1b604
"""

from typing import Sequence, Union

from alembic import op


revision: str = "8d3f2a9c1b70"
down_revision: Union[str, Sequence[str], None] = "f8c2d9a1b604"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _mapping_immutability_function(contract_comparison: str) -> str:
    return f"""
        CREATE OR REPLACE FUNCTION ire.enforce_system_record_import_mapping_immutability()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'PENDING'
                    OR NEW.reviewed_by IS NOT NULL
                    OR NEW.reviewed_at IS NOT NULL
                    OR NEW.review_note IS NOT NULL THEN
                    RAISE EXCEPTION 'A system-record import mapping must be submitted pending review';
                END IF;
                RETURN NEW;
            END IF;
            IF NEW.id IS DISTINCT FROM OLD.id
                OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                OR NEW.domain_id IS DISTINCT FROM OLD.domain_id
                OR NEW.mapping_name IS DISTINCT FROM OLD.mapping_name
                OR NEW.source_system IS DISTINCT FROM OLD.source_system
                OR {contract_comparison}
                OR NEW.contract_sha256 IS DISTINCT FROM OLD.contract_sha256
                OR NEW.author_id IS DISTINCT FROM OLD.author_id
                OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'System-record import mappings are immutable after submission';
            END IF;
            IF OLD.status <> 'PENDING' THEN
                RAISE EXCEPTION 'A reviewed system-record import mapping cannot be changed';
            END IF;
            IF NEW.status NOT IN ('APPROVED', 'REJECTED')
                OR NEW.reviewed_by IS NULL
                OR NEW.reviewed_at IS NULL THEN
                RAISE EXCEPTION 'A pending mapping may only transition once to an attributed review';
            END IF;
            IF NEW.reviewed_by = OLD.author_id THEN
                RAISE EXCEPTION 'A mapping author cannot approve or reject their own mapping';
            END IF;
            IF NEW.status = 'REJECTED' AND (NEW.review_note IS NULL OR length(trim(NEW.review_note)) = 0) THEN
                RAISE EXCEPTION 'A mapping rejection requires a reason';
            END IF;
            RETURN NEW;
        END;
        $$
    """


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE institutional_data_sources ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE institutional_data_sources FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_institutional_data_sources
        ON institutional_data_sources
        FOR ALL
        USING (
            tenant_id = ire.current_tenant_id()
            AND ire.tenant_owns_domain(tenant_id, domain_id)
        )
        WITH CHECK (
            tenant_id = ire.current_tenant_id()
            AND ire.tenant_owns_domain(tenant_id, domain_id)
        )
    """)
    op.execute(
        _mapping_immutability_function(
            "NEW.contract::jsonb IS DISTINCT FROM OLD.contract::jsonb"
        )
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        _mapping_immutability_function("NEW.contract IS DISTINCT FROM OLD.contract")
    )
    op.execute("DROP POLICY IF EXISTS tenant_isolation_institutional_data_sources ON institutional_data_sources")
    op.execute("ALTER TABLE institutional_data_sources NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE institutional_data_sources DISABLE ROW LEVEL SECURITY")
