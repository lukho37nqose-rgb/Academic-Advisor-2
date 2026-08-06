"""add OCR provenance, structure, and review triage

Revision ID: a6c3b2e91d75
Revises: f4a1b7d83e25
"""

from alembic import op
import sqlalchemy as sa


revision = "a6c3b2e91d75"
down_revision = "f4a1b7d83e25"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("handbook_pages") as batch_op:
        batch_op.add_column(sa.Column("extraction_kind", sa.String(), nullable=False, server_default="SELECTABLE_TEXT"))
        batch_op.add_column(sa.Column("review_priority", sa.String(), nullable=False, server_default="NORMAL"))

    with op.batch_alter_table("handbook_ocr_reviews") as batch_op:
        batch_op.add_column(sa.Column("provider_model_version", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("provider_response_hash", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("source_page_hash", sa.String(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("proposed_blocks", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("quality_signals", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("review_priority", sa.String(), nullable=False, server_default="NORMAL"))
        batch_op.create_index("ix_handbook_ocr_reviews_priority", ["handbook_id", "review_priority"])


def downgrade() -> None:
    with op.batch_alter_table("handbook_ocr_reviews") as batch_op:
        batch_op.drop_index("ix_handbook_ocr_reviews_priority")
        batch_op.drop_column("review_priority")
        batch_op.drop_column("quality_signals")
        batch_op.drop_column("proposed_blocks")
        batch_op.drop_column("source_page_hash")
        batch_op.drop_column("provider_response_hash")
        batch_op.drop_column("provider_model_version")

    with op.batch_alter_table("handbook_pages") as batch_op:
        batch_op.drop_column("review_priority")
        batch_op.drop_column("extraction_kind")
