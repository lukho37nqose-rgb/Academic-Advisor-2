"""Add governed, non-operative shadow calibration records.

Revision ID: fa2d7c1e9b04
Revises: e3b9a4c6d712
Create Date: 2026-07-26 14:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "fa2d7c1e9b04"
down_revision: Union[str, Sequence[str], None] = "e3b9a4c6d712"
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
        "shadow_calibration_suites",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("domain_id", sa.String(), nullable=False),
        sa.Column("release_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("data_basis", sa.String(), nullable=False),
        sa.Column("privacy_approval_reference", sa.String(), nullable=True),
        sa.Column("policy_as_of_date", sa.Date(), nullable=False),
        sa.Column("author_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("input_sha256", sa.String(), nullable=False),
        sa.Column("certified_by", sa.String(), nullable=True),
        sa.Column("certification_note", sa.Text(), nullable=True),
        sa.Column("certified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.CheckConstraint(
            "status IN ('SUBMITTED', 'CERTIFIED', 'COMPLETED')",
            name="ck_shadow_calibration_suite_status",
        ),
        sa.CheckConstraint(
            "data_basis IN ('SYNTHETIC', 'APPROVED_DEIDENTIFIED')",
            name="ck_shadow_calibration_suite_data_basis",
        ),
        sa.ForeignKeyConstraint(["domain_id"], ["domains.id"]),
        sa.ForeignKeyConstraint(["release_id"], ["releases.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shadow_calibration_suites_tenant_id", "shadow_calibration_suites", ["tenant_id"])
    op.create_index("ix_shadow_calibration_suites_domain_id", "shadow_calibration_suites", ["domain_id"])
    op.create_index("ix_shadow_calibration_suites_release_id", "shadow_calibration_suites", ["release_id"])
    op.create_index("ix_shadow_calibration_suites_status", "shadow_calibration_suites", ["status"])

    op.create_table(
        "shadow_calibration_cases",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("suite_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("domain_id", sa.String(), nullable=False),
        sa.Column("case_reference", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("recorded_decision", sa.String(), nullable=False),
        sa.Column("recorded_outcome_reference", sa.Text(), nullable=False),
        sa.Column("facts", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.CheckConstraint(
            "recorded_decision IN ('ELIGIBLE', 'INELIGIBLE', 'NEEDS_MANUAL_REVIEW')",
            name="ck_shadow_calibration_case_recorded_decision",
        ),
        sa.ForeignKeyConstraint(["suite_id"], ["shadow_calibration_suites.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("suite_id", "case_reference", name="uq_shadow_calibration_case_reference"),
    )
    op.create_index("ix_shadow_calibration_cases_suite_id", "shadow_calibration_cases", ["suite_id"])
    op.create_index("ix_shadow_calibration_cases_tenant_id", "shadow_calibration_cases", ["tenant_id"])
    op.create_index("ix_shadow_calibration_cases_domain_id", "shadow_calibration_cases", ["domain_id"])

    op.create_table(
        "shadow_calibration_suite_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("suite_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("domain_id", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.CheckConstraint(
            "event_type IN ('SUBMITTED', 'CERTIFIED', 'COMPLETED')",
            name="ck_shadow_calibration_suite_event_type",
        ),
        sa.ForeignKeyConstraint(["suite_id"], ["shadow_calibration_suites.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("suite_id", "sequence", name="uq_shadow_calibration_suite_event_sequence"),
    )
    op.create_index("ix_shadow_calibration_suite_events_suite_id", "shadow_calibration_suite_events", ["suite_id"])
    op.create_index("ix_shadow_calibration_suite_events_tenant_id", "shadow_calibration_suite_events", ["tenant_id"])
    op.create_index("ix_shadow_calibration_suite_events_domain_id", "shadow_calibration_suite_events", ["domain_id"])

    op.create_table(
        "shadow_calibration_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("suite_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("domain_id", sa.String(), nullable=False),
        sa.Column("release_id", sa.String(), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("report_sha256", sa.String(), nullable=False),
        sa.Column("executed_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["release_id"], ["releases.id"]),
        sa.ForeignKeyConstraint(["suite_id"], ["shadow_calibration_suites.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("suite_id"),
    )
    op.create_index("ix_shadow_calibration_runs_tenant_id", "shadow_calibration_runs", ["tenant_id"])
    op.create_index("ix_shadow_calibration_runs_domain_id", "shadow_calibration_runs", ["domain_id"])

    op.create_table(
        "shadow_calibration_findings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("domain_id", sa.String(), nullable=False),
        sa.Column("expected_decision", sa.String(), nullable=False),
        sa.Column("actual_decision", sa.String(), nullable=False),
        sa.Column("input_sha256", sa.String(), nullable=False),
        sa.Column("trace_sha256", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("classification", sa.String(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.String(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.CheckConstraint("status IN ('OPEN', 'RESOLVED')", name="ck_shadow_calibration_finding_status"),
        sa.CheckConstraint(
            "classification IN ('SOURCE_DATA', 'POLICY_MODEL', 'EVIDENCE', 'GOVERNANCE') OR classification IS NULL",
            name="ck_shadow_calibration_finding_classification",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["shadow_calibration_cases.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["shadow_calibration_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "case_id", name="uq_shadow_calibration_finding_case"),
    )
    op.create_index("ix_shadow_calibration_findings_run_id", "shadow_calibration_findings", ["run_id"])
    op.create_index("ix_shadow_calibration_findings_case_id", "shadow_calibration_findings", ["case_id"])
    op.create_index("ix_shadow_calibration_findings_tenant_id", "shadow_calibration_findings", ["tenant_id"])
    op.create_index("ix_shadow_calibration_findings_domain_id", "shadow_calibration_findings", ["domain_id"])
    op.create_index("ix_shadow_calibration_findings_status", "shadow_calibration_findings", ["status"])

    if op.get_bind().dialect.name != "postgresql":
        return

    tables = (
        "shadow_calibration_suites",
        "shadow_calibration_cases",
        "shadow_calibration_suite_events",
        "shadow_calibration_runs",
        "shadow_calibration_findings",
    )
    for table_name in tables:
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        _tenant_domain_policy(table_name)

    op.execute("""
        CREATE OR REPLACE FUNCTION ire.prevent_shadow_calibration_case_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'Shadow calibration cases are immutable after submission';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER enforce_shadow_calibration_case_immutability
        BEFORE UPDATE OR DELETE ON shadow_calibration_cases
        FOR EACH ROW EXECUTE FUNCTION ire.prevent_shadow_calibration_case_mutation()
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION ire.enforce_shadow_calibration_suite_lifecycle()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                OR NEW.domain_id IS DISTINCT FROM OLD.domain_id
                OR NEW.release_id IS DISTINCT FROM OLD.release_id
                OR NEW.name IS DISTINCT FROM OLD.name
                OR NEW.description IS DISTINCT FROM OLD.description
                OR NEW.data_basis IS DISTINCT FROM OLD.data_basis
                OR NEW.privacy_approval_reference IS DISTINCT FROM OLD.privacy_approval_reference
                OR NEW.policy_as_of_date IS DISTINCT FROM OLD.policy_as_of_date
                OR NEW.author_id IS DISTINCT FROM OLD.author_id
                OR NEW.input_sha256 IS DISTINCT FROM OLD.input_sha256
                OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'Shadow calibration input is immutable after submission';
            END IF;
            IF OLD.status = 'SUBMITTED' AND NEW.status = 'CERTIFIED'
                AND NEW.certified_by IS NOT NULL AND NEW.certification_note IS NOT NULL
                AND NEW.certified_at IS NOT NULL AND NEW.completed_at IS NULL THEN
                RETURN NEW;
            END IF;
            IF OLD.status = 'CERTIFIED' AND NEW.status = 'COMPLETED'
                AND NEW.completed_at IS NOT NULL THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'Invalid shadow calibration suite lifecycle transition';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER enforce_shadow_calibration_suite_lifecycle
        BEFORE UPDATE OR DELETE ON shadow_calibration_suites
        FOR EACH ROW EXECUTE FUNCTION ire.enforce_shadow_calibration_suite_lifecycle()
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION ire.enforce_shadow_calibration_run_immutability()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'Shadow calibration reports are immutable';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER enforce_shadow_calibration_run_immutability
        BEFORE UPDATE OR DELETE ON shadow_calibration_runs
        FOR EACH ROW EXECUTE FUNCTION ire.enforce_shadow_calibration_run_immutability()
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION ire.enforce_shadow_calibration_finding_lifecycle()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Shadow calibration findings cannot be deleted';
            END IF;
            IF NEW.run_id IS DISTINCT FROM OLD.run_id
                OR NEW.case_id IS DISTINCT FROM OLD.case_id
                OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                OR NEW.domain_id IS DISTINCT FROM OLD.domain_id
                OR NEW.expected_decision IS DISTINCT FROM OLD.expected_decision
                OR NEW.actual_decision IS DISTINCT FROM OLD.actual_decision
                OR NEW.input_sha256 IS DISTINCT FROM OLD.input_sha256
                OR NEW.trace_sha256 IS DISTINCT FROM OLD.trace_sha256
                OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'Shadow calibration finding evidence is immutable';
            END IF;
            IF OLD.status = 'OPEN' AND NEW.status = 'RESOLVED'
                AND NEW.classification IS NOT NULL AND NEW.resolution_note IS NOT NULL
                AND NEW.resolved_by IS NOT NULL AND NEW.resolved_at IS NOT NULL THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'Invalid shadow calibration finding lifecycle transition';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER enforce_shadow_calibration_finding_lifecycle
        BEFORE UPDATE OR DELETE ON shadow_calibration_findings
        FOR EACH ROW EXECUTE FUNCTION ire.enforce_shadow_calibration_finding_lifecycle()
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION ire.prevent_shadow_calibration_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'Shadow calibration events are append-only';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER enforce_shadow_calibration_event_append_only
        BEFORE UPDATE OR DELETE ON shadow_calibration_suite_events
        FOR EACH ROW EXECUTE FUNCTION ire.prevent_shadow_calibration_event_mutation()
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        trigger_tables = (
            ("enforce_shadow_calibration_event_append_only", "shadow_calibration_suite_events"),
            ("enforce_shadow_calibration_finding_lifecycle", "shadow_calibration_findings"),
            ("enforce_shadow_calibration_run_immutability", "shadow_calibration_runs"),
            ("enforce_shadow_calibration_suite_lifecycle", "shadow_calibration_suites"),
            ("enforce_shadow_calibration_case_immutability", "shadow_calibration_cases"),
        )
        for trigger_name, table_name in trigger_tables:
            op.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_name}")
        for function_name in (
            "ire.prevent_shadow_calibration_event_mutation()",
            "ire.enforce_shadow_calibration_finding_lifecycle()",
            "ire.enforce_shadow_calibration_run_immutability()",
            "ire.enforce_shadow_calibration_suite_lifecycle()",
            "ire.prevent_shadow_calibration_case_mutation()",
        ):
            op.execute(f"DROP FUNCTION IF EXISTS {function_name}")
        for table_name in (
            "shadow_calibration_findings",
            "shadow_calibration_runs",
            "shadow_calibration_suite_events",
            "shadow_calibration_cases",
            "shadow_calibration_suites",
        ):
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table_name} ON {table_name}")
            op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_shadow_calibration_findings_status", table_name="shadow_calibration_findings")
    op.drop_index("ix_shadow_calibration_findings_domain_id", table_name="shadow_calibration_findings")
    op.drop_index("ix_shadow_calibration_findings_tenant_id", table_name="shadow_calibration_findings")
    op.drop_index("ix_shadow_calibration_findings_case_id", table_name="shadow_calibration_findings")
    op.drop_index("ix_shadow_calibration_findings_run_id", table_name="shadow_calibration_findings")
    op.drop_table("shadow_calibration_findings")
    op.drop_index("ix_shadow_calibration_runs_domain_id", table_name="shadow_calibration_runs")
    op.drop_index("ix_shadow_calibration_runs_tenant_id", table_name="shadow_calibration_runs")
    op.drop_table("shadow_calibration_runs")
    op.drop_index("ix_shadow_calibration_suite_events_domain_id", table_name="shadow_calibration_suite_events")
    op.drop_index("ix_shadow_calibration_suite_events_tenant_id", table_name="shadow_calibration_suite_events")
    op.drop_index("ix_shadow_calibration_suite_events_suite_id", table_name="shadow_calibration_suite_events")
    op.drop_table("shadow_calibration_suite_events")
    op.drop_index("ix_shadow_calibration_cases_domain_id", table_name="shadow_calibration_cases")
    op.drop_index("ix_shadow_calibration_cases_tenant_id", table_name="shadow_calibration_cases")
    op.drop_index("ix_shadow_calibration_cases_suite_id", table_name="shadow_calibration_cases")
    op.drop_table("shadow_calibration_cases")
    op.drop_index("ix_shadow_calibration_suites_status", table_name="shadow_calibration_suites")
    op.drop_index("ix_shadow_calibration_suites_release_id", table_name="shadow_calibration_suites")
    op.drop_index("ix_shadow_calibration_suites_domain_id", table_name="shadow_calibration_suites")
    op.drop_index("ix_shadow_calibration_suites_tenant_id", table_name="shadow_calibration_suites")
    op.drop_table("shadow_calibration_suites")
