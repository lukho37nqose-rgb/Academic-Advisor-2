"""Add tenant-scoped evidence and epistemic records.

Revision ID: c4d8f2a7e913
Revises: a19d8c2f4b61
Create Date: 2026-07-25 16:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4d8f2a7e913'
down_revision: Union[str, Sequence[str], None] = 'a19d8c2f4b61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEGACY_SCOPE = "'__legacy_unscoped__'"


def upgrade() -> None:
    """Bind evidence and traces to a tenant/domain and retain claim/fact lineage."""
    op.add_column(
        'evidence',
        sa.Column('tenant_id', sa.String(), server_default=sa.text(_LEGACY_SCOPE), nullable=False),
    )
    op.add_column(
        'evidence',
        sa.Column('domain_id', sa.String(), server_default=sa.text(_LEGACY_SCOPE), nullable=False),
    )
    op.create_index('ix_evidence_tenant_id', 'evidence', ['tenant_id'])
    op.create_index('ix_evidence_domain_id', 'evidence', ['domain_id'])

    op.add_column(
        'reasoning_graphs',
        sa.Column('tenant_id', sa.String(), server_default=sa.text(_LEGACY_SCOPE), nullable=False),
    )
    op.add_column(
        'reasoning_graphs',
        sa.Column('domain_id', sa.String(), server_default=sa.text(_LEGACY_SCOPE), nullable=False),
    )
    op.add_column('reasoning_graphs', sa.Column('release_id', sa.String(), nullable=True))
    op.add_column('reasoning_graphs', sa.Column('evidence_id', sa.String(), nullable=True))
    op.create_index('ix_reasoning_graphs_tenant_id', 'reasoning_graphs', ['tenant_id'])
    op.create_index('ix_reasoning_graphs_domain_id', 'reasoning_graphs', ['domain_id'])
    if op.get_bind().dialect.name != 'sqlite':
        op.create_foreign_key(
            'fk_reasoning_graphs_release_id', 'reasoning_graphs', 'releases', ['release_id'], ['id']
        )
        op.create_foreign_key(
            'fk_reasoning_graphs_evidence_id', 'reasoning_graphs', 'evidence', ['evidence_id'], ['id']
        )

    with op.batch_alter_table('releases') as batch:
        batch.create_unique_constraint('uq_release_domain_version', ['domain_id', 'version'])

    op.create_table(
        'claims',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('domain_id', sa.String(), nullable=False),
        sa.Column('evidence_id', sa.String(), nullable=False),
        sa.Column('reasoning_graph_id', sa.String(), nullable=False),
        sa.Column('target_path', sa.String(), nullable=False),
        sa.Column('asserted_value', sa.JSON(), nullable=False),
        sa.Column('extraction_confidence', sa.Float(), nullable=False),
        sa.Column('source_trust_level', sa.Float(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('source_quote', sa.Text(), nullable=True),
        sa.Column('source_locator', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['evidence_id'], ['evidence.id']),
        sa.ForeignKeyConstraint(['reasoning_graph_id'], ['reasoning_graphs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_claims_tenant_id', 'claims', ['tenant_id'])
    op.create_index('ix_claims_domain_id', 'claims', ['domain_id'])
    op.create_index('ix_claims_evidence_id', 'claims', ['evidence_id'])
    op.create_index('ix_claims_reasoning_graph_id', 'claims', ['reasoning_graph_id'])

    op.create_table(
        'facts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('domain_id', sa.String(), nullable=False),
        sa.Column('reasoning_graph_id', sa.String(), nullable=False),
        sa.Column('target_path', sa.String(), nullable=False),
        sa.Column('resolved_value', sa.JSON(), nullable=True),
        sa.Column('final_confidence', sa.Float(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('supporting_claim_ids', sa.JSON(), nullable=False),
        sa.Column('rejected_claim_ids', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['reasoning_graph_id'], ['reasoning_graphs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_facts_tenant_id', 'facts', ['tenant_id'])
    op.create_index('ix_facts_domain_id', 'facts', ['domain_id'])
    op.create_index('ix_facts_reasoning_graph_id', 'facts', ['reasoning_graph_id'])


def downgrade() -> None:
    """Remove traceability additions."""
    op.drop_index('ix_facts_reasoning_graph_id', table_name='facts')
    op.drop_index('ix_facts_domain_id', table_name='facts')
    op.drop_index('ix_facts_tenant_id', table_name='facts')
    op.drop_table('facts')

    op.drop_index('ix_claims_reasoning_graph_id', table_name='claims')
    op.drop_index('ix_claims_evidence_id', table_name='claims')
    op.drop_index('ix_claims_domain_id', table_name='claims')
    op.drop_index('ix_claims_tenant_id', table_name='claims')
    op.drop_table('claims')

    with op.batch_alter_table('releases') as batch:
        batch.drop_constraint('uq_release_domain_version', type_='unique')

    if op.get_bind().dialect.name != 'sqlite':
        op.drop_constraint('fk_reasoning_graphs_evidence_id', 'reasoning_graphs', type_='foreignkey')
        op.drop_constraint('fk_reasoning_graphs_release_id', 'reasoning_graphs', type_='foreignkey')
    op.drop_index('ix_reasoning_graphs_domain_id', table_name='reasoning_graphs')
    op.drop_index('ix_reasoning_graphs_tenant_id', table_name='reasoning_graphs')
    op.drop_column('reasoning_graphs', 'evidence_id')
    op.drop_column('reasoning_graphs', 'release_id')
    op.drop_column('reasoning_graphs', 'domain_id')
    op.drop_column('reasoning_graphs', 'tenant_id')

    op.drop_index('ix_evidence_domain_id', table_name='evidence')
    op.drop_index('ix_evidence_tenant_id', table_name='evidence')
    op.drop_column('evidence', 'domain_id')
    op.drop_column('evidence', 'tenant_id')
