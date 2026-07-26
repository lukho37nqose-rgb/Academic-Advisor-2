"""Add manual support requests.

Revision ID: d7a3f5c9b214
Revises: c4d8f2a7e913
Create Date: 2026-07-25 17:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd7a3f5c9b214'
down_revision: Union[str, Sequence[str], None] = 'c4d8f2a7e913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'support_requests',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('domain_id', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('contact_details', sa.Text(), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='OPEN'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_support_requests_tenant_id', 'support_requests', ['tenant_id'])
    op.create_index('ix_support_requests_domain_id', 'support_requests', ['domain_id'])


def downgrade() -> None:
    op.drop_index('ix_support_requests_domain_id', table_name='support_requests')
    op.drop_index('ix_support_requests_tenant_id', table_name='support_requests')
    op.drop_table('support_requests')
