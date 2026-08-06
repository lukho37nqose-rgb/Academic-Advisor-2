"""add signed release source manifest hash

Revision ID: f0d9c6a2b581
Revises: d5e1a4b8c923
"""

from alembic import op
import sqlalchemy as sa


revision = "f0d9c6a2b581"
down_revision = "d5e1a4b8c923"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("releases") as batch_op:
        batch_op.add_column(sa.Column("source_manifest_hash", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("releases") as batch_op:
        batch_op.drop_column("source_manifest_hash")
