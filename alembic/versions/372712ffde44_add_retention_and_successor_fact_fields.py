"""add retention and successor fact fields

Revision ID: 372712ffde44
Revises: e4c7f2a8b916
Create Date: 2026-07-26 16:32:10.562814

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '372712ffde44'
down_revision: Union[str, Sequence[str], None] = 'e4c7f2a8b916'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'evidence_deletion_events',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('evidence_id', sa.String(), sa.ForeignKey('evidence.id'), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('domain_id', sa.String(), nullable=False),
        sa.Column('actor_id', sa.String(), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('evidence_id', name='uq_evidence_deletion_event_evidence'),
    )
    op.create_table(
        'fact_supersession_events',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('old_fact_id', sa.String(), sa.ForeignKey('facts.id'), nullable=False),
        sa.Column('new_fact_id', sa.String(), sa.ForeignKey('facts.id'), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('domain_id', sa.String(), nullable=False),
        sa.Column('actor_id', sa.String(), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('old_fact_id', name='uq_fact_supersession_event_old_fact'),
    )
    op.create_table(
        'reasoning_graph_deletion_events',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('reasoning_graph_id', sa.String(), sa.ForeignKey('reasoning_graphs.id'), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('domain_id', sa.String(), nullable=False),
        sa.Column('actor_id', sa.String(), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    )
    if op.get_bind().dialect.name == 'postgresql':
        for table_name in (
            'evidence_deletion_events',
            'fact_supersession_events',
            'reasoning_graph_deletion_events',
        ):
            op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
            op.execute(f'''
                CREATE POLICY tenant_isolation_{table_name}
                ON {table_name} FOR ALL
                USING (
                    tenant_id = ire.current_tenant_id()
                    AND ire.tenant_owns_domain(tenant_id, domain_id)
                )
                WITH CHECK (
                    tenant_id = ire.current_tenant_id()
                    AND ire.tenant_owns_domain(tenant_id, domain_id)
                )
            ''')
            op.execute(
                f"CREATE TRIGGER prevent_{table_name}_mutation BEFORE UPDATE OR DELETE ON {table_name} "
                "FOR EACH ROW EXECUTE FUNCTION ire.prevent_decision_artifact_mutation()"
            )
    # Evidence retention
    with op.batch_alter_table('evidence') as batch_op:
        batch_op.add_column(sa.Column('retention_expires_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('deletion_reason', sa.String(), nullable=True))

    # Fact retention and successor workflow
    with op.batch_alter_table('facts') as batch_op:
        batch_op.add_column(sa.Column('retention_expires_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('deletion_reason', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('superseded_by_fact_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('superseding_reason', sa.String(), nullable=True))
        batch_op.create_foreign_key('fk_facts_superseded_by', 'facts', ['superseded_by_fact_id'], ['id'])

    # Reasoning graph retention
    with op.batch_alter_table('reasoning_graphs') as batch_op:
        batch_op.add_column(sa.Column('retention_expires_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('deletion_reason', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name == 'postgresql':
        for table_name in (
            'reasoning_graph_deletion_events',
            'fact_supersession_events',
            'evidence_deletion_events',
        ):
            op.execute(f"DROP TRIGGER IF EXISTS prevent_{table_name}_mutation ON {table_name}")
    op.drop_table('reasoning_graph_deletion_events')
    op.drop_table('fact_supersession_events')
    op.drop_table('evidence_deletion_events')
    # Reasoning graph retention
    with op.batch_alter_table('reasoning_graphs') as batch_op:
        batch_op.drop_column('deletion_reason')
        batch_op.drop_column('deleted_at')
        batch_op.drop_column('retention_expires_at')

    # Fact retention and successor workflow
    with op.batch_alter_table('facts') as batch_op:
        batch_op.drop_constraint('fk_facts_superseded_by', type_='foreignkey')
        batch_op.drop_column('superseding_reason')
        batch_op.drop_column('superseded_at')
        batch_op.drop_column('superseded_by_fact_id')
        batch_op.drop_column('deletion_reason')
        batch_op.drop_column('deleted_at')
        batch_op.drop_column('retention_expires_at')

    # Evidence retention
    with op.batch_alter_table('evidence') as batch_op:
        batch_op.drop_column('deletion_reason')
        batch_op.drop_column('deleted_at')
        batch_op.drop_column('retention_expires_at')
