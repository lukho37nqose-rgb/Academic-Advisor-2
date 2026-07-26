"""Add response deadlines and retention fields to assistance requests.

Revision ID: f9a3c6e2b518
Revises: e8b6f2d4c917
Create Date: 2026-07-25 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f9a3c6e2b518'
down_revision: Union[str, Sequence[str], None] = 'e8b6f2d4c917'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('support_requests', sa.Column('response_due_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('support_requests', sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('support_requests', sa.Column('retention_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_support_requests_response_due_at', 'support_requests', ['response_due_at'])
    op.create_index('ix_support_requests_retention_expires_at', 'support_requests', ['retention_expires_at'])


def downgrade() -> None:
    op.drop_index('ix_support_requests_retention_expires_at', table_name='support_requests')
    op.drop_index('ix_support_requests_response_due_at', table_name='support_requests')
    op.drop_column('support_requests', 'retention_expires_at')
    op.drop_column('support_requests', 'closed_at')
    op.drop_column('support_requests', 'response_due_at')
