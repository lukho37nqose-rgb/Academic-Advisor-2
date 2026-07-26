"""Add a durable, tenant-scoped queue for handbook processing.

Revision ID: e3b9a4c6d712
Revises: d2e6f1a8b903
Create Date: 2026-07-26 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e3b9a4c6d712"
down_revision: Union[str, Sequence[str], None] = "d2e6f1a8b903"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("domain_id", sa.String(), nullable=False),
        sa.Column("job_type", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("deduplication_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="QUEUED"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "job_type IN ('HANDBOOK_TEXT_EXTRACTION', 'HANDBOOK_OCR')",
            name="ck_background_job_type",
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'DEAD_LETTER')",
            name="ck_background_job_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_background_job_attempts"),
        sa.CheckConstraint("max_attempts BETWEEN 1 AND 10", name="ck_background_job_max_attempts"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["domain_id"], ["domains.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "deduplication_key", name="uq_background_job_deduplication"),
    )
    op.create_index("ix_background_jobs_tenant_id", "background_jobs", ["tenant_id"])
    op.create_index("ix_background_jobs_domain_id", "background_jobs", ["domain_id"])
    op.create_index("ix_background_jobs_status", "background_jobs", ["status"])
    op.create_index("ix_background_jobs_available_at", "background_jobs", ["available_at"])
    op.create_index("ix_background_jobs_lease_expires_at", "background_jobs", ["lease_expires_at"])
    op.create_index(
        "ix_background_jobs_tenant_status_available",
        "background_jobs",
        ["tenant_id", "status", "available_at"],
    )

    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE background_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE background_jobs FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_background_jobs
        ON background_jobs
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


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation_background_jobs ON background_jobs")
        op.execute("ALTER TABLE background_jobs NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE background_jobs DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_background_jobs_tenant_status_available", table_name="background_jobs")
    op.drop_index("ix_background_jobs_lease_expires_at", table_name="background_jobs")
    op.drop_index("ix_background_jobs_available_at", table_name="background_jobs")
    op.drop_index("ix_background_jobs_status", table_name="background_jobs")
    op.drop_index("ix_background_jobs_domain_id", table_name="background_jobs")
    op.drop_index("ix_background_jobs_tenant_id", table_name="background_jobs")
    op.drop_table("background_jobs")
