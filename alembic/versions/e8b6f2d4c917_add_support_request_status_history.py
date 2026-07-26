"""Add assistance workflow status history.

Revision ID: e8b6f2d4c917
Revises: d7a3f5c9b214
Create Date: 2026-07-25 18:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e8b6f2d4c917'
down_revision: Union[str, Sequence[str], None] = 'd7a3f5c9b214'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'support_request_events',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('support_request_id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('domain_id', sa.String(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('actor_id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['support_request_id'], ['support_requests.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('support_request_id', 'sequence', name='uq_support_request_event_sequence'),
    )
    op.create_index('ix_support_request_events_support_request_id', 'support_request_events', ['support_request_id'])
    op.create_index('ix_support_request_events_tenant_id', 'support_request_events', ['tenant_id'])
    op.create_index('ix_support_request_events_domain_id', 'support_request_events', ['domain_id'])


def downgrade() -> None:
    op.drop_index('ix_support_request_events_domain_id', table_name='support_request_events')
    op.drop_index('ix_support_request_events_tenant_id', table_name='support_request_events')
    op.drop_index('ix_support_request_events_support_request_id', table_name='support_request_events')
    op.drop_table('support_request_events')
