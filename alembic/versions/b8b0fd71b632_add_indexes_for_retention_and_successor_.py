"""add indexes for retention and successor fields

Revision ID: b8b0fd71b632
Revises: 372712ffde44
Create Date: 2026-07-26 17:38:50.699381

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8b0fd71b632'
down_revision: Union[str, Sequence[str], None] = '372712ffde44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('ix_evidence_deleted_at', 'evidence', ['deleted_at'])
    op.create_index('ix_evidence_retention_expires_at', 'evidence', ['retention_expires_at'])
    
    op.create_index('ix_facts_deleted_at', 'facts', ['deleted_at'])
    op.create_index('ix_facts_retention_expires_at', 'facts', ['retention_expires_at'])
    op.create_index('ix_facts_superseded_by_fact_id', 'facts', ['superseded_by_fact_id'])
    
    op.create_index('ix_reasoning_graphs_deleted_at', 'reasoning_graphs', ['deleted_at'])
    op.create_index('ix_reasoning_graphs_retention_expires_at', 'reasoning_graphs', ['retention_expires_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_reasoning_graphs_retention_expires_at', table_name='reasoning_graphs')
    op.drop_index('ix_reasoning_graphs_deleted_at', table_name='reasoning_graphs')
    
    op.drop_index('ix_facts_superseded_by_fact_id', table_name='facts')
    op.drop_index('ix_facts_retention_expires_at', table_name='facts')
    op.drop_index('ix_facts_deleted_at', table_name='facts')
    
    op.drop_index('ix_evidence_retention_expires_at', table_name='evidence')
    op.drop_index('ix_evidence_deleted_at', table_name='evidence')
