"""Add tenant-scoped, reviewed system-record import mappings.

Revision ID: d2e6f1a8b903
Revises: c8f4a2d7e613
Create Date: 2026-07-26 05:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2e6f1a8b903"
down_revision: Union[str, Sequence[str], None] = "c8f4a2d7e613"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_record_import_mappings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("domain_id", sa.String(), nullable=False),
        sa.Column("mapping_name", sa.String(), nullable=False),
        sa.Column("source_system", sa.String(), nullable=False),
        sa.Column("contract", sa.JSON(), nullable=False),
        sa.Column("contract_sha256", sa.String(), nullable=False),
        sa.Column("author_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_system_record_import_mapping_status",
        ),
        sa.CheckConstraint(
            "length(contract_sha256) = 64",
            name="ck_system_record_import_mapping_contract_hash",
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND reviewed_by IS NULL AND reviewed_at IS NULL) "
            "OR (status IN ('APPROVED', 'REJECTED') AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_system_record_import_mapping_review_state",
        ),
        sa.CheckConstraint(
            "status <> 'REJECTED' OR review_note IS NOT NULL",
            name="ck_system_record_import_mapping_rejection_note",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["domain_id"], ["domains.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_system_record_import_mappings_tenant_id", "system_record_import_mappings", ["tenant_id"])
    op.create_index("ix_system_record_import_mappings_domain_id", "system_record_import_mappings", ["domain_id"])
    op.create_index("ix_system_record_import_mappings_status", "system_record_import_mappings", ["status"])
    op.create_index(
        "ix_system_record_import_mappings_tenant_domain_status",
        "system_record_import_mappings",
        ["tenant_id", "domain_id", "status"],
    )

    op.create_table(
        "system_record_import_mapping_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("mapping_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("domain_id", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "event_type IN ('SUBMITTED', 'APPROVED', 'REJECTED')",
            name="ck_system_record_import_mapping_event_type",
        ),
        sa.ForeignKeyConstraint(["mapping_id"], ["system_record_import_mappings.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mapping_id", "sequence", name="uq_system_record_import_mapping_event_sequence"),
    )
    op.create_index("ix_system_record_import_mapping_events_mapping_id", "system_record_import_mapping_events", ["mapping_id"])
    op.create_index("ix_system_record_import_mapping_events_tenant_id", "system_record_import_mapping_events", ["tenant_id"])
    op.create_index("ix_system_record_import_mapping_events_domain_id", "system_record_import_mapping_events", ["domain_id"])

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table_name in ("system_record_import_mappings", "system_record_import_mapping_events"):
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation_{table_name}
            ON {table_name}
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

    op.execute("""
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
                OR NEW.contract IS DISTINCT FROM OLD.contract
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
    """)
    op.execute("""
        CREATE TRIGGER enforce_system_record_import_mapping_immutability
        BEFORE INSERT OR UPDATE ON system_record_import_mappings
        FOR EACH ROW EXECUTE FUNCTION ire.enforce_system_record_import_mapping_immutability()
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION ire.enforce_system_record_import_mapping_event_lifecycle()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            mapping_status text;
            mapping_author_id text;
            mapping_reviewer_id text;
            mapping_review_note text;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'System-record import mapping events are append-only';
            END IF;
            SELECT status, author_id, reviewed_by, review_note
            INTO mapping_status, mapping_author_id, mapping_reviewer_id, mapping_review_note
            FROM system_record_import_mappings
            WHERE id = NEW.mapping_id
                AND tenant_id = NEW.tenant_id
                AND domain_id = NEW.domain_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'A mapping event must belong to a visible mapping in the same tenant and domain';
            END IF;
            IF NEW.sequence = 1
                AND NEW.event_type = 'SUBMITTED'
                AND NEW.actor_id = mapping_author_id
                AND mapping_status = 'PENDING'
                AND NEW.note IS NULL THEN
                RETURN NEW;
            END IF;
            IF NEW.sequence = 2
                AND NEW.event_type = mapping_status
                AND mapping_status IN ('APPROVED', 'REJECTED')
                AND NEW.actor_id = mapping_reviewer_id
                AND NEW.note IS NOT DISTINCT FROM mapping_review_note THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'System-record import mapping event does not match the mapping lifecycle';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER enforce_system_record_import_mapping_event_lifecycle
        BEFORE INSERT OR UPDATE OR DELETE ON system_record_import_mapping_events
        FOR EACH ROW EXECUTE FUNCTION ire.enforce_system_record_import_mapping_event_lifecycle()
    """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS enforce_system_record_import_mapping_event_lifecycle "
            "ON system_record_import_mapping_events"
        )
        op.execute("DROP FUNCTION IF EXISTS ire.enforce_system_record_import_mapping_event_lifecycle()")
        op.execute(
            "DROP TRIGGER IF EXISTS enforce_system_record_import_mapping_immutability "
            "ON system_record_import_mappings"
        )
        op.execute("DROP FUNCTION IF EXISTS ire.enforce_system_record_import_mapping_immutability()")
        for table_name in ("system_record_import_mapping_events", "system_record_import_mappings"):
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table_name} ON {table_name}")
            op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_system_record_import_mapping_events_domain_id", table_name="system_record_import_mapping_events")
    op.drop_index("ix_system_record_import_mapping_events_tenant_id", table_name="system_record_import_mapping_events")
    op.drop_index("ix_system_record_import_mapping_events_mapping_id", table_name="system_record_import_mapping_events")
    op.drop_table("system_record_import_mapping_events")
    op.drop_index("ix_system_record_import_mappings_tenant_domain_status", table_name="system_record_import_mappings")
    op.drop_index("ix_system_record_import_mappings_status", table_name="system_record_import_mappings")
    op.drop_index("ix_system_record_import_mappings_domain_id", table_name="system_record_import_mappings")
    op.drop_index("ix_system_record_import_mappings_tenant_id", table_name="system_record_import_mappings")
    op.drop_table("system_record_import_mappings")
