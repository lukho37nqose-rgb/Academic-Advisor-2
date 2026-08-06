"""add signed release workflows and held outbox

Revision ID: c3d9a012f782
Revises: b8b0fd71b632
"""

from alembic import op
import sqlalchemy as sa


revision = "c3d9a012f782"
down_revision = "b8b0fd71b632"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("releases") as batch_op:
        batch_op.add_column(sa.Column("workflows", sa.JSON(), nullable=True))

    op.create_table(
        "workflow_outbox",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("domain_id", sa.String(), sa.ForeignKey("domains.id"), nullable=False),
        sa.Column("release_id", sa.String(), sa.ForeignKey("releases.id"), nullable=False),
        sa.Column("reasoning_graph_id", sa.String(), sa.ForeignKey("reasoning_graphs.id"), nullable=False),
        sa.Column("workflow_id", sa.String(), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("action_payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="HELD"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_workflow_outbox_idempotency"),
        sa.CheckConstraint("status IN ('HELD', 'SHADOW_READY', 'CANCELLED')", name="ck_workflow_outbox_status"),
    )
    op.create_index("ix_workflow_outbox_tenant_id", "workflow_outbox", ["tenant_id"])
    op.create_index("ix_workflow_outbox_domain_id", "workflow_outbox", ["domain_id"])
    op.create_index("ix_workflow_outbox_release_id", "workflow_outbox", ["release_id"])
    op.create_index("ix_workflow_outbox_reasoning_graph_id", "workflow_outbox", ["reasoning_graph_id"])
    op.create_index("ix_workflow_outbox_status", "workflow_outbox", ["status"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE workflow_outbox ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE workflow_outbox FORCE ROW LEVEL SECURITY")
        op.execute('''
            CREATE POLICY tenant_isolation_workflow_outbox ON workflow_outbox FOR ALL
            USING (tenant_id = ire.current_tenant_id() AND ire.tenant_owns_domain(tenant_id, domain_id))
            WITH CHECK (tenant_id = ire.current_tenant_id() AND ire.tenant_owns_domain(tenant_id, domain_id))
        ''')


def downgrade() -> None:
    op.drop_table("workflow_outbox")
    with op.batch_alter_table("releases") as batch_op:
        batch_op.drop_column("workflows")
