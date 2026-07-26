"""Add handbook upload jobs and page extraction checkpoints.

Revision ID: a6d2e1f9c403
Revises: f9a3c6e2b518
Create Date: 2026-07-25 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a6d2e1f9c403'
down_revision: Union[str, Sequence[str], None] = 'f9a3c6e2b518'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'handbook_uploads',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('domain_id', sa.String(), nullable=False),
        sa.Column('file_name', sa.String(), nullable=False),
        sa.Column('content_type', sa.String(), nullable=False),
        sa.Column('file_size_bytes', sa.Integer(), nullable=False),
        sa.Column('content_hash', sa.String(), nullable=False),
        sa.Column('storage_key', sa.String(), nullable=False),
        sa.Column('uploaded_by', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='QUEUED'),
        sa.Column('total_pages', sa.Integer(), nullable=True),
        sa.Column('processed_pages', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_handbook_uploads_tenant_id', 'handbook_uploads', ['tenant_id'])
    op.create_index('ix_handbook_uploads_domain_id', 'handbook_uploads', ['domain_id'])
    op.create_index('ix_handbook_uploads_content_hash', 'handbook_uploads', ['content_hash'])
    op.create_table(
        'handbook_pages',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('handbook_id', sa.String(), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=False),
        sa.Column('text_content', sa.Text(), nullable=False),
        sa.Column('content_hash', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['handbook_id'], ['handbook_uploads.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('handbook_id', 'page_number', name='uq_handbook_page_number'),
    )
    op.create_index('ix_handbook_pages_handbook_id', 'handbook_pages', ['handbook_id'])


def downgrade() -> None:
    op.drop_index('ix_handbook_pages_handbook_id', table_name='handbook_pages')
    op.drop_table('handbook_pages')
    op.drop_index('ix_handbook_uploads_content_hash', table_name='handbook_uploads')
    op.drop_index('ix_handbook_uploads_domain_id', table_name='handbook_uploads')
    op.drop_index('ix_handbook_uploads_tenant_id', table_name='handbook_uploads')
    op.drop_table('handbook_uploads')
