"""add evidence provenance and record currency

Revision ID: d7f4b8e29a61
Revises: c3d9a012f782
"""

from alembic import op
import sqlalchemy as sa


revision = "d7f4b8e29a61"
down_revision = "c3d9a012f782"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("evidence") as batch_op:
        batch_op.add_column(sa.Column("source_authority", sa.String(), nullable=False, server_default="subject_submitted"))
        batch_op.add_column(sa.Column("record_state", sa.String(), nullable=False, server_default="provisional"))
        batch_op.add_column(sa.Column("source_system", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("source_record_version", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("source_as_of", sa.DateTime(timezone=True), nullable=True))
    # Preserve the known semantics of already-ingested ERP evidence rather than
    # retroactively presenting it as a subject submission.
    op.execute("UPDATE evidence SET source_authority = 'official_system', record_state = 'confirmed' WHERE source_type = 'erp_system'")


def downgrade() -> None:
    with op.batch_alter_table("evidence") as batch_op:
        batch_op.drop_column("source_as_of")
        batch_op.drop_column("source_record_version")
        batch_op.drop_column("source_system")
        batch_op.drop_column("record_state")
        batch_op.drop_column("source_authority")
