"""Add review-only OCR proposals for scanned handbook pages.

Revision ID: c9f2a7d4e615
Revises: b8e4c1f7a922
Create Date: 2026-07-25 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9f2a7d4e615'
down_revision: Union[str, Sequence[str], None] = 'b8e4c1f7a922'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'handbook_ocr_reviews',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('handbook_id', sa.String(), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=False),
        sa.Column('provider_name', sa.String(), nullable=False),
        sa.Column('provider_reference', sa.String(), nullable=True),
        sa.Column('proposed_text', sa.Text(), nullable=False),
        sa.Column('proposed_text_hash', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='PENDING_REVIEW'),
        sa.Column('reviewed_text', sa.Text(), nullable=True),
        sa.Column('reviewed_by', sa.String(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['handbook_id'], ['handbook_uploads.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('handbook_id', 'page_number', name='uq_handbook_ocr_review_page'),
    )
    op.create_index('ix_handbook_ocr_reviews_tenant_id', 'handbook_ocr_reviews', ['tenant_id'])
    op.create_index('ix_handbook_ocr_reviews_handbook_id', 'handbook_ocr_reviews', ['handbook_id'])
    op.create_table(
        'handbook_ocr_review_events',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('ocr_review_id', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('actor_id', sa.String(), nullable=False),
        sa.Column('text_hash', sa.String(), nullable=True),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['ocr_review_id'], ['handbook_ocr_reviews.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ocr_review_id', 'sequence', name='uq_handbook_ocr_review_event_sequence'),
    )
    op.create_index('ix_handbook_ocr_review_events_ocr_review_id', 'handbook_ocr_review_events', ['ocr_review_id'])


def downgrade() -> None:
    op.drop_index('ix_handbook_ocr_review_events_ocr_review_id', table_name='handbook_ocr_review_events')
    op.drop_table('handbook_ocr_review_events')
    op.drop_index('ix_handbook_ocr_reviews_handbook_id', table_name='handbook_ocr_reviews')
    op.drop_index('ix_handbook_ocr_reviews_tenant_id', table_name='handbook_ocr_reviews')
    op.drop_table('handbook_ocr_reviews')
