"""Add constrained direct handbook upload sessions.

Revision ID: b8e4c1f7a922
Revises: a6d2e1f9c403
Create Date: 2026-07-25 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8e4c1f7a922'
down_revision: Union[str, Sequence[str], None] = 'a6d2e1f9c403'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('handbook_uploads') as batch_op:
        batch_op.alter_column('content_hash', existing_type=sa.String(), nullable=True)

    op.create_table(
        'handbook_upload_sessions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('domain_id', sa.String(), nullable=False),
        sa.Column('file_name', sa.String(), nullable=False),
        sa.Column('content_type', sa.String(), nullable=False),
        sa.Column('file_size_bytes', sa.Integer(), nullable=False),
        sa.Column('storage_key', sa.String(), nullable=False),
        sa.Column('uploaded_by', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='PENDING'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('storage_key'),
    )
    op.create_index('ix_handbook_upload_sessions_tenant_id', 'handbook_upload_sessions', ['tenant_id'])
    op.create_index('ix_handbook_upload_sessions_domain_id', 'handbook_upload_sessions', ['domain_id'])
    op.create_index('ix_handbook_upload_sessions_expires_at', 'handbook_upload_sessions', ['expires_at'])


def downgrade() -> None:
    op.drop_index('ix_handbook_upload_sessions_expires_at', table_name='handbook_upload_sessions')
    op.drop_index('ix_handbook_upload_sessions_domain_id', table_name='handbook_upload_sessions')
    op.drop_index('ix_handbook_upload_sessions_tenant_id', table_name='handbook_upload_sessions')
    op.drop_table('handbook_upload_sessions')
    op.execute("UPDATE handbook_uploads SET content_hash = '' WHERE content_hash IS NULL")
    with op.batch_alter_table('handbook_uploads') as batch_op:
        batch_op.alter_column('content_hash', existing_type=sa.String(), nullable=False)
