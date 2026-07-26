"""Require independently reviewed evidence facts before deterministic evaluation.

Revision ID: b4e6f1a9d205
Revises: a1c5e8d9f304
Create Date: 2026-07-26 20:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4e6f1a9d205"
down_revision: Union[str, Sequence[str], None] = "a1c5e8d9f304"
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
        "evidence_fact_proposals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("domain_id", sa.String(), nullable=False),
        sa.Column("evidence_id", sa.String(), nullable=False),
        sa.Column("subject_id", sa.String(), nullable=False),
        sa.Column("target_path", sa.String(), nullable=False),
        sa.Column("asserted_value", sa.JSON(), nullable=True),
        sa.Column("source_quote", sa.Text(), nullable=False),
        sa.Column("source_locator", sa.String(), nullable=True),
        sa.Column("extraction_confidence", sa.Float(), nullable=False),
        sa.Column("source_trust_level", sa.Float(), nullable=False),
        sa.Column("proposal_origin", sa.String(), nullable=False, server_default="MANUAL"),
        sa.Column("evidence_sha256", sa.String(), nullable=False),
        sa.Column("input_sha256", sa.String(), nullable=False),
        sa.Column("proposed_by", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'REJECTED')",
            name="ck_evidence_fact_proposal_status",
        ),
        sa.CheckConstraint(
            "extraction_confidence >= 0 AND extraction_confidence <= 1",
            name="ck_evidence_fact_proposal_extraction_confidence",
        ),
        sa.CheckConstraint(
            "source_trust_level >= 0 AND source_trust_level <= 1",
            name="ck_evidence_fact_proposal_source_trust",
        ),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("tenant_id", "domain_id", "evidence_id", "target_path", "status"):
        op.create_index(f"ix_evidence_fact_proposals_{column}", "evidence_fact_proposals", [column])
    op.create_index(
        "uq_evidence_fact_proposal_accepted_target",
        "evidence_fact_proposals",
        ["evidence_id", "target_path"],
        unique=True,
        postgresql_where=sa.text("status = 'ACCEPTED'"),
        sqlite_where=sa.text("status = 'ACCEPTED'"),
    )

    op.create_table(
        "evidence_fact_proposal_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("proposal_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("domain_id", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.CheckConstraint(
            "action IN ('SUBMITTED', 'ACCEPTED', 'REJECTED')",
            name="ck_evidence_fact_proposal_event_action",
        ),
        sa.ForeignKeyConstraint(["proposal_id"], ["evidence_fact_proposals.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proposal_id", "sequence", name="uq_evidence_fact_proposal_event_sequence"),
    )
    for column in ("proposal_id", "tenant_id", "domain_id"):
        op.create_index(f"ix_evidence_fact_proposal_events_{column}", "evidence_fact_proposal_events", [column])

    if op.get_bind().dialect.name != "postgresql":
        return

    for table_name in ("evidence_fact_proposals", "evidence_fact_proposal_events"):
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        _tenant_domain_policy(table_name)

    op.execute("""
        CREATE OR REPLACE FUNCTION ire.enforce_evidence_fact_proposal_lifecycle()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Evidence fact proposals cannot be deleted';
            END IF;
            IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                OR NEW.domain_id IS DISTINCT FROM OLD.domain_id
                OR NEW.evidence_id IS DISTINCT FROM OLD.evidence_id
                OR NEW.subject_id IS DISTINCT FROM OLD.subject_id
                OR NEW.target_path IS DISTINCT FROM OLD.target_path
                OR NEW.asserted_value IS DISTINCT FROM OLD.asserted_value
                OR NEW.source_quote IS DISTINCT FROM OLD.source_quote
                OR NEW.source_locator IS DISTINCT FROM OLD.source_locator
                OR NEW.extraction_confidence IS DISTINCT FROM OLD.extraction_confidence
                OR NEW.source_trust_level IS DISTINCT FROM OLD.source_trust_level
                OR NEW.proposal_origin IS DISTINCT FROM OLD.proposal_origin
                OR NEW.evidence_sha256 IS DISTINCT FROM OLD.evidence_sha256
                OR NEW.input_sha256 IS DISTINCT FROM OLD.input_sha256
                OR NEW.proposed_by IS DISTINCT FROM OLD.proposed_by
                OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'Evidence fact proposal input is immutable after submission';
            END IF;
            IF OLD.status = 'PENDING' AND NEW.status IN ('ACCEPTED', 'REJECTED')
                AND NEW.reviewed_by IS NOT NULL
                AND NEW.review_note IS NOT NULL
                AND NEW.reviewed_at IS NOT NULL
                AND NEW.reviewed_by IS DISTINCT FROM OLD.proposed_by THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'Invalid evidence fact proposal lifecycle transition';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER enforce_evidence_fact_proposal_lifecycle
        BEFORE UPDATE OR DELETE ON evidence_fact_proposals
        FOR EACH ROW EXECUTE FUNCTION ire.enforce_evidence_fact_proposal_lifecycle()
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION ire.enforce_evidence_fact_proposal_event_append_only()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'Evidence fact proposal events are append-only';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER enforce_evidence_fact_proposal_event_append_only
        BEFORE UPDATE OR DELETE ON evidence_fact_proposal_events
        FOR EACH ROW EXECUTE FUNCTION ire.enforce_evidence_fact_proposal_event_append_only()
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION ire.enforce_evidence_fact_proposal_event_insert()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            proposal_status text;
            proposal_author text;
        BEGIN
            SELECT status, proposed_by INTO proposal_status, proposal_author
            FROM evidence_fact_proposals
            WHERE id = NEW.proposal_id
                AND tenant_id = NEW.tenant_id
                AND domain_id = NEW.domain_id;
            IF proposal_status IS NULL THEN
                RAISE EXCEPTION 'Evidence fact proposal event has no matching proposal';
            END IF;
            IF NEW.sequence = 1 AND NEW.action = 'SUBMITTED'
                AND proposal_status = 'PENDING' AND NEW.actor_id = proposal_author THEN
                RETURN NEW;
            END IF;
            IF NEW.sequence = 2 AND NEW.action IN ('ACCEPTED', 'REJECTED')
                AND proposal_status = NEW.action
                AND NEW.note IS NOT NULL
                AND NEW.actor_id IS DISTINCT FROM proposal_author THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'Evidence fact proposal event does not match its lifecycle';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER enforce_evidence_fact_proposal_event_insert
        BEFORE INSERT ON evidence_fact_proposal_events
        FOR EACH ROW EXECUTE FUNCTION ire.enforce_evidence_fact_proposal_event_insert()
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION ire.verify_evidence_fact_proposal_event()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.status = 'PENDING' AND EXISTS (
                SELECT 1 FROM evidence_fact_proposal_events event
                WHERE event.proposal_id = NEW.id
                    AND event.tenant_id = NEW.tenant_id
                    AND event.domain_id = NEW.domain_id
                    AND event.sequence = 1
                    AND event.action = 'SUBMITTED'
                    AND event.actor_id = NEW.proposed_by
            ) THEN
                RETURN NULL;
            END IF;
            IF NEW.status IN ('ACCEPTED', 'REJECTED') AND EXISTS (
                SELECT 1 FROM evidence_fact_proposal_events event
                WHERE event.proposal_id = NEW.id
                    AND event.tenant_id = NEW.tenant_id
                    AND event.domain_id = NEW.domain_id
                    AND event.sequence = 2
                    AND event.action = NEW.status
                    AND event.actor_id = NEW.reviewed_by
                    AND event.note = NEW.review_note
                    AND event.actor_id IS DISTINCT FROM NEW.proposed_by
            ) THEN
                RETURN NULL;
            END IF;
            RAISE EXCEPTION 'Evidence fact proposal has no matching append-only event';
        END;
        $$
    """)
    op.execute("""
        CREATE CONSTRAINT TRIGGER verify_evidence_fact_proposal_event
        AFTER INSERT OR UPDATE ON evidence_fact_proposals
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION ire.verify_evidence_fact_proposal_event()
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for trigger in (
            "verify_evidence_fact_proposal_event",
            "enforce_evidence_fact_proposal_event_insert",
            "enforce_evidence_fact_proposal_event_append_only",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON evidence_fact_proposal_events")
        op.execute("DROP TRIGGER IF EXISTS enforce_evidence_fact_proposal_lifecycle ON evidence_fact_proposals")
        for function in (
            "ire.verify_evidence_fact_proposal_event()",
            "ire.enforce_evidence_fact_proposal_event_insert()",
            "ire.enforce_evidence_fact_proposal_event_append_only()",
            "ire.enforce_evidence_fact_proposal_lifecycle()",
        ):
            op.execute(f"DROP FUNCTION IF EXISTS {function}")
    op.drop_table("evidence_fact_proposal_events")
    op.drop_table("evidence_fact_proposals")
