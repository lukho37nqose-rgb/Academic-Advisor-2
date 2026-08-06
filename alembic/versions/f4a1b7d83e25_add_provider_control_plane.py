"""add isolated provider control-plane metadata

Revision ID: f4a1b7d83e25
Revises: e1a6c8f93d24
"""

from alembic import op
import sqlalchemy as sa


revision = "f4a1b7d83e25"
down_revision = "e1a6c8f93d24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_tenant_controls",
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("lifecycle_state", sa.String(), nullable=False, server_default="PILOT"),
        sa.Column("service_tier", sa.String(), nullable=False, server_default="pilot"),
        sa.Column("integration_status", sa.String(), nullable=False, server_default="NOT_CONFIGURED"),
        sa.Column("integration_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("lifecycle_state IN ('PILOT', 'ACTIVE', 'SUSPENDED', 'DECOMMISSIONED')", name="ck_provider_tenant_lifecycle"),
    )
    op.create_table(
        "provider_support_access_requests",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("requested_by", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="REQUESTED"),
        sa.Column("approved_by", sa.String(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("status IN ('REQUESTED', 'APPROVED', 'REJECTED', 'CLOSED')", name="ck_provider_support_access_status"),
    )
    op.create_index("ix_provider_support_access_requests_tenant_id", "provider_support_access_requests", ["tenant_id"])
    op.create_index("ix_provider_support_access_requests_status", "provider_support_access_requests", ["status"])
    if op.get_bind().dialect.name == "postgresql":
        for table in ("provider_tenant_controls", "provider_support_access_requests"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(f"CREATE POLICY provider_control_{table} ON {table} FOR ALL USING (current_setting('ire.access_mode', true) = 'provider') WITH CHECK (current_setting('ire.access_mode', true) = 'provider')")
        op.execute("CREATE POLICY provider_control_tenants ON tenants FOR ALL USING (current_setting('ire.access_mode', true) = 'provider') WITH CHECK (current_setting('ire.access_mode', true) = 'provider')")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS provider_control_tenants ON tenants")
    op.drop_index("ix_provider_support_access_requests_status", table_name="provider_support_access_requests")
    op.drop_index("ix_provider_support_access_requests_tenant_id", table_name="provider_support_access_requests")
    op.drop_table("provider_support_access_requests")
    op.drop_table("provider_tenant_controls")
