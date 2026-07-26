"""Add governed institutional context events for temporal transparency.

Revision ID: a1c5e8d9f304
Revises: fa2d7c1e9b04
Create Date: 2026-07-26 16:45:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1c5e8d9f304"
down_revision: Union[str, Sequence[str], None] = "fa2d7c1e9b04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tenant_domain_policy(table_name: str) -> None:
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


def upgrade() -> None:
    op.create_table(
        "institutional_context_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("domain_id", sa.String(), nullable=False),
        sa.Column("subject_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("student_summary", sa.Text(), nullable=False),
        sa.Column("institutional_effect", sa.Text(), nullable=False),
        sa.Column("authority_name", sa.String(), nullable=False),
        sa.Column("authority_reference", sa.String(), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_until", sa.Date(), nullable=True),
        sa.Column("visibility", sa.String(), nullable=False),
        sa.Column("policy_release_id", sa.String(), nullable=True),
        sa.Column("policy_citation", sa.Text(), nullable=True),
        sa.Column("predecessor_event_id", sa.String(), nullable=True),
        sa.Column("predecessor_relationship", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("input_sha256", sa.String(), nullable=False),
        sa.Column("recorded_by", sa.String(), nullable=False),
        sa.Column("attested_by", sa.String(), nullable=True),
        sa.Column("attestation_note", sa.Text(), nullable=True),
        sa.Column("attested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.CheckConstraint(
            "event_type IN ('CONCESSION', 'CURRICULUM_APPLICABILITY', 'ASSESSMENT_ACCOMMODATION', "
            "'APPEAL_OUTCOME', 'REGISTRATION_POSITION', 'PROGRESSION_POSITION', 'GRADUATION_POSITION', 'OTHER')",
            name="ck_institutional_context_event_type",
        ),
        sa.CheckConstraint("visibility IN ('SUBJECT', 'STAFF_ONLY')", name="ck_institutional_context_visibility"),
        sa.CheckConstraint("status IN ('SUBMITTED', 'CERTIFIED', 'REJECTED')", name="ck_institutional_context_status"),
        sa.CheckConstraint(
            "effective_until IS NULL OR effective_until >= effective_from",
            name="ck_institutional_context_effective_period",
        ),
        sa.CheckConstraint(
            "predecessor_relationship IN ('SUPERSEDES', 'REVOKES') OR predecessor_relationship IS NULL",
            name="ck_institutional_context_predecessor_relationship",
        ),
        sa.CheckConstraint(
            "(predecessor_event_id IS NULL AND predecessor_relationship IS NULL) "
            "OR (predecessor_event_id IS NOT NULL AND predecessor_relationship IS NOT NULL)",
            name="ck_institutional_context_predecessor_pair",
        ),
        sa.ForeignKeyConstraint(["domain_id"], ["domains.id"]),
        sa.ForeignKeyConstraint(["policy_release_id"], ["releases.id"]),
        sa.ForeignKeyConstraint(["predecessor_event_id"], ["institutional_context_events.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_institutional_context_events_tenant_id", "institutional_context_events", ["tenant_id"])
    op.create_index("ix_institutional_context_events_domain_id", "institutional_context_events", ["domain_id"])
    op.create_index("ix_institutional_context_events_subject_id", "institutional_context_events", ["subject_id"])
    op.create_index("ix_institutional_context_events_policy_release_id", "institutional_context_events", ["policy_release_id"])
    op.create_index("ix_institutional_context_events_predecessor_event_id", "institutional_context_events", ["predecessor_event_id"])
    op.create_index("ix_institutional_context_events_status", "institutional_context_events", ["status"])

    op.create_table(
        "institutional_context_event_attestations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("context_event_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("domain_id", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.CheckConstraint("action IN ('SUBMITTED', 'CERTIFIED', 'REJECTED')", name="ck_institutional_context_attestation_action"),
        sa.ForeignKeyConstraint(["context_event_id"], ["institutional_context_events.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("context_event_id", "sequence", name="uq_institutional_context_attestation_sequence"),
    )
    op.create_index("ix_institutional_context_event_attestations_context_event_id", "institutional_context_event_attestations", ["context_event_id"])
    op.create_index("ix_institutional_context_event_attestations_tenant_id", "institutional_context_event_attestations", ["tenant_id"])
    op.create_index("ix_institutional_context_event_attestations_domain_id", "institutional_context_event_attestations", ["domain_id"])

    if op.get_bind().dialect.name != "postgresql":
        return

    for table_name in ("institutional_context_events", "institutional_context_event_attestations"):
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        _tenant_domain_policy(table_name)

    op.execute("""
        CREATE OR REPLACE FUNCTION ire.enforce_institutional_context_event_lifecycle()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Institutional context events cannot be deleted';
            END IF;
            IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                OR NEW.domain_id IS DISTINCT FROM OLD.domain_id
                OR NEW.subject_id IS DISTINCT FROM OLD.subject_id
                OR NEW.event_type IS DISTINCT FROM OLD.event_type
                OR NEW.title IS DISTINCT FROM OLD.title
                OR NEW.student_summary IS DISTINCT FROM OLD.student_summary
                OR NEW.institutional_effect IS DISTINCT FROM OLD.institutional_effect
                OR NEW.authority_name IS DISTINCT FROM OLD.authority_name
                OR NEW.authority_reference IS DISTINCT FROM OLD.authority_reference
                OR NEW.source_reference IS DISTINCT FROM OLD.source_reference
                OR NEW.event_date IS DISTINCT FROM OLD.event_date
                OR NEW.effective_from IS DISTINCT FROM OLD.effective_from
                OR NEW.effective_until IS DISTINCT FROM OLD.effective_until
                OR NEW.visibility IS DISTINCT FROM OLD.visibility
                OR NEW.policy_release_id IS DISTINCT FROM OLD.policy_release_id
                OR NEW.policy_citation IS DISTINCT FROM OLD.policy_citation
                OR NEW.predecessor_event_id IS DISTINCT FROM OLD.predecessor_event_id
                OR NEW.predecessor_relationship IS DISTINCT FROM OLD.predecessor_relationship
                OR NEW.input_sha256 IS DISTINCT FROM OLD.input_sha256
                OR NEW.recorded_by IS DISTINCT FROM OLD.recorded_by
                OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'Institutional context input is immutable after submission';
            END IF;
            IF OLD.status = 'SUBMITTED' AND NEW.status IN ('CERTIFIED', 'REJECTED')
                AND NEW.attested_by IS NOT NULL AND NEW.attestation_note IS NOT NULL
                AND NEW.attested_at IS NOT NULL
                AND NEW.attested_by IS DISTINCT FROM OLD.recorded_by THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'Invalid institutional context event lifecycle transition';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER enforce_institutional_context_event_lifecycle
        BEFORE UPDATE OR DELETE ON institutional_context_events
        FOR EACH ROW EXECUTE FUNCTION ire.enforce_institutional_context_event_lifecycle()
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION ire.prevent_institutional_context_attestation_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'Institutional context attestations are append-only';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER enforce_institutional_context_attestation_append_only
        BEFORE UPDATE OR DELETE ON institutional_context_event_attestations
        FOR EACH ROW EXECUTE FUNCTION ire.prevent_institutional_context_attestation_mutation()
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION ire.enforce_institutional_context_attestation_insert()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            context_status text;
            context_recorded_by text;
        BEGIN
            SELECT status, recorded_by INTO context_status, context_recorded_by
            FROM institutional_context_events
            WHERE id = NEW.context_event_id
                AND tenant_id = NEW.tenant_id
                AND domain_id = NEW.domain_id;
            IF context_status IS NULL THEN
                RAISE EXCEPTION 'Institutional context attestation has no matching event';
            END IF;
            IF NEW.sequence = 1 AND NEW.action = 'SUBMITTED'
                AND context_status = 'SUBMITTED' AND NEW.actor_id = context_recorded_by THEN
                RETURN NEW;
            END IF;
            IF NEW.sequence = 2 AND NEW.action IN ('CERTIFIED', 'REJECTED')
                AND context_status = NEW.action AND NEW.note IS NOT NULL
                AND NEW.actor_id IS DISTINCT FROM context_recorded_by THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'Institutional context attestation does not match its event lifecycle';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER enforce_institutional_context_attestation_insert
        BEFORE INSERT ON institutional_context_event_attestations
        FOR EACH ROW EXECUTE FUNCTION ire.enforce_institutional_context_attestation_insert()
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION ire.verify_institutional_context_event_attestation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.status = 'SUBMITTED' AND EXISTS (
                SELECT 1
                FROM institutional_context_event_attestations attestation
                WHERE attestation.context_event_id = NEW.id
                    AND attestation.tenant_id = NEW.tenant_id
                    AND attestation.domain_id = NEW.domain_id
                    AND attestation.sequence = 1
                    AND attestation.action = 'SUBMITTED'
                    AND attestation.actor_id = NEW.recorded_by
            ) THEN
                RETURN NULL;
            END IF;
            IF NEW.status IN ('CERTIFIED', 'REJECTED') AND EXISTS (
                SELECT 1
                FROM institutional_context_event_attestations attestation
                WHERE attestation.context_event_id = NEW.id
                    AND attestation.tenant_id = NEW.tenant_id
                    AND attestation.domain_id = NEW.domain_id
                    AND attestation.sequence = 2
                    AND attestation.action = NEW.status
                    AND attestation.actor_id = NEW.attested_by
                    AND attestation.note = NEW.attestation_note
                    AND attestation.actor_id IS DISTINCT FROM NEW.recorded_by
            ) THEN
                RETURN NULL;
            END IF;
            RAISE EXCEPTION 'Institutional context event has no matching append-only attestation';
        END;
        $$
    """)
    op.execute("""
        CREATE CONSTRAINT TRIGGER verify_institutional_context_event_attestation
        AFTER INSERT OR UPDATE OF status ON institutional_context_events
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION ire.verify_institutional_context_event_attestation()
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS enforce_institutional_context_attestation_insert ON institutional_context_event_attestations")
        op.execute("DROP TRIGGER IF EXISTS enforce_institutional_context_attestation_append_only ON institutional_context_event_attestations")
        op.execute("DROP TRIGGER IF EXISTS verify_institutional_context_event_attestation ON institutional_context_events")
        op.execute("DROP TRIGGER IF EXISTS enforce_institutional_context_event_lifecycle ON institutional_context_events")
        op.execute("DROP FUNCTION IF EXISTS ire.prevent_institutional_context_attestation_mutation()")
        op.execute("DROP FUNCTION IF EXISTS ire.verify_institutional_context_event_attestation()")
        op.execute("DROP FUNCTION IF EXISTS ire.enforce_institutional_context_attestation_insert()")
        op.execute("DROP FUNCTION IF EXISTS ire.enforce_institutional_context_event_lifecycle()")
        for table_name in ("institutional_context_event_attestations", "institutional_context_events"):
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table_name} ON {table_name}")
            op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_institutional_context_event_attestations_domain_id", table_name="institutional_context_event_attestations")
    op.drop_index("ix_institutional_context_event_attestations_tenant_id", table_name="institutional_context_event_attestations")
    op.drop_index("ix_institutional_context_event_attestations_context_event_id", table_name="institutional_context_event_attestations")
    op.drop_table("institutional_context_event_attestations")
    op.drop_index("ix_institutional_context_events_status", table_name="institutional_context_events")
    op.drop_index("ix_institutional_context_events_predecessor_event_id", table_name="institutional_context_events")
    op.drop_index("ix_institutional_context_events_policy_release_id", table_name="institutional_context_events")
    op.drop_index("ix_institutional_context_events_subject_id", table_name="institutional_context_events")
    op.drop_index("ix_institutional_context_events_domain_id", table_name="institutional_context_events")
    op.drop_index("ix_institutional_context_events_tenant_id", table_name="institutional_context_events")
    op.drop_table("institutional_context_events")
